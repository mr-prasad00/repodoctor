"""FastAPI entrypoint for RepoDoctor's single-report MVP pipeline."""

from __future__ import annotations

import sys
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = str(Path(cur_dir).parent)
if cur_dir not in sys.path:
    sys.path.insert(0, cur_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

load_dotenv(Path(cur_dir).parent / ".env")

try:
    from backend.db import init_db, persist_analysis
    from backend.extractor import extract
    from backend.models import AnalysisResult
    from backend.sandbox import run_test
    from backend.test_generator import generate_test
    from backend.verdict import decide_verdict
except ModuleNotFoundError:
    from db import init_db, persist_analysis
    from extractor import extract
    from models import AnalysisResult
    from sandbox import run_test
    from test_generator import generate_test
    from verdict import decide_verdict


app = FastAPI(title="RepoDoctor")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
allowed_origins = ["*"] if frontend_origin == "*" else [frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    title: str
    body: str
    provider: Optional[str] = None


@app.on_event("startup")
def initialise_database() -> None:
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "RepoDoctor API",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/providers")
def get_available_providers() -> dict[str, Any]:
    """Check which AI provider API keys are active in the environment."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    grok_key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    has_gemini = bool(gemini_key and gemini_key not in ("your_gemini_api_key", "", None, "]"))
    has_openai = bool(openai_key and openai_key not in ("your_openai_api_key", "", None))
    has_groq = bool(groq_key and groq_key not in ("your_groq_api_key", "", None))
    has_grok = bool(grok_key and grok_key not in ("your_grok_api_key", "", None))
    has_openrouter = bool(openrouter_key and openrouter_key not in ("your_openrouter_api_key", "", None))

    default_provider = "gemini"
    if has_gemini:
        default_provider = "gemini"
    elif has_openai:
        default_provider = "openai"
    elif has_groq:
        default_provider = "groq"
    elif has_grok:
        default_provider = "grok"
    elif has_openrouter:
        default_provider = "openrouter"

    return {
        "providers": {
            "gemini": has_gemini,
            "openai": has_openai,
            "groq": has_groq,
            "grok": has_grok,
            "openrouter": has_openrouter
        },
        "default": default_provider
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    """Extract, test, decide, and persist a single pasted bug report."""
    if not request.title.strip() or not request.body.strip():
        raise HTTPException(status_code=422, detail="title and body must not be blank")

    try:
        result = run_pipeline(request.title, request.body, request.provider)
        persist_analysis(request.title, request.body, result)
        return _response_body(result)
    except Exception as error:
        err_msg = str(error)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            raise HTTPException(
                status_code=429,
                detail="AI provider rate limit exceeded. Please wait a minute and try again.",
            )
        elif "400" in err_msg or "API_KEY_INVALID" in err_msg:
            raise HTTPException(
                status_code=400,
                detail="AI provider API Key is invalid. Please check your .env configuration.",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected pipeline error: {err_msg}",
            )


def run_pipeline(title: str, body: str, provider: str | None = None) -> AnalysisResult:
    """Run the MVP pipeline, treating untestable reports as insufficient info."""
    started_at = perf_counter()
    extracted: dict[str, Any] | None = None
    generated_test: str | None = None
    run_output: str | None = None

    try:
        extracted = dict(extract(title, body, provider))
    except ValueError as error:
        return _result(
            "insufficient_info",
            extracted,
            generated_test,
            run_output,
            f"Need more info: could not extract a valid reproduction ({error}).",
            started_at,
        )

    missing = [field for field in ("function", "inputs", "expected") if extracted.get(field) is None]
    if missing:
        return _result(
            decide_verdict(missing_fields=True),
            extracted,
            generated_test,
            run_output,
            f"Need more info: missing {', '.join(missing)}.",
            started_at,
        )

    try:
        generated_test = generate_test(extracted)
    except ValueError as error:
        return _result(
            decide_verdict(invalid=True),
            extracted,
            generated_test,
            run_output,
            f"Need more info: generated test is invalid ({error}).",
            started_at,
        )

    sandbox_result = run_test(generated_test)
    run_output = sandbox_result["output"]
    status = decide_verdict(sandbox_result)
    if sandbox_result["timed_out"]:
        explanation = "Need more info: generated test timed out after 10 seconds."
    elif status == "insufficient_info":
        explanation = "Need more info: test execution failed with an error (e.g. function does not exist)."
    elif status == "reproduced":
        explanation = "Discrepancy reproduced — maintainer to confirm intended behavior."
    else:
        explanation = "Couldn't reproduce — code returns the expected value."
    return _result(status, extracted, generated_test, run_output, explanation, started_at)


def _result(
    status: str,
    extracted: dict[str, Any] | None,
    generated_test: str | None,
    run_output: str | None,
    explanation: str,
    started_at: float,
) -> AnalysisResult:
    return AnalysisResult(
        status=status,
        extracted=extracted,
        generated_test=generated_test,
        run_output=run_output,
        explanation=explanation,
        duration_ms=round((perf_counter() - started_at) * 1000),
    )


def _response_body(result: AnalysisResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "extracted": result.extracted,
        "generated_test": result.generated_test,
        "run_output": result.run_output,
        "explanation": result.explanation,
        "duration_ms": result.duration_ms,
    }


@app.post("/analyze-document")
async def analyze_document(
    file: UploadFile = File(...),
    provider: Optional[str] = Form(None)
) -> dict[str, Any]:
    """Parse, split, run reproduction pipeline on each claim in a document, and persist results."""
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {e}")

    try:
        from backend.parser import parse_document
    except ModuleNotFoundError:
        from parser import parse_document

    raw_text = parse_document(content, file.filename or "document.txt")
    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in document")

    try:
        from backend.splitter import split_document
    except ModuleNotFoundError:
        from splitter import split_document

    try:
        bugs = split_document(raw_text, provider)
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            raise HTTPException(
                status_code=429,
                detail="AI provider rate limit exceeded. Please wait a minute and try again.",
            )
        elif "400" in err_msg or "API_KEY_INVALID" in err_msg:
            raise HTTPException(
                status_code=400,
                detail="AI provider API Key is invalid. Please check your .env configuration.",
            )
        # Fallback to single bug if splitter fails for other reasons
        bugs = [{"title": file.filename or "Uploaded Document", "body": raw_text}]

    if not bugs:
        bugs = [{"title": file.filename or "Uploaded Document", "body": raw_text}]

    results: list[tuple[str, str, AnalysisResult]] = []
    response_results = []
    
    for i, bug in enumerate(bugs, start=1):
        title = bug.get("title", f"Bug #{i}").strip()
        body = bug.get("body", "").strip()
        
        try:
            res = run_pipeline(title, body, provider)
        except Exception as error:
            err_msg = str(error)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                raise HTTPException(
                    status_code=429,
                    detail="AI provider rate limit exceeded. Please wait a minute and try again.",
                )
            elif "400" in err_msg or "API_KEY_INVALID" in err_msg:
                raise HTTPException(
                    status_code=400,
                    detail="AI provider API Key is invalid. Please check your .env configuration.",
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Unexpected pipeline error: {err_msg}",
                )

        results.append((title, body, res))
        response_results.append({
            "seq": i,
            "status": res.status,
            "explanation": res.explanation
        })

    try:
        from backend.db import persist_document_batch
    except ModuleNotFoundError:
        from db import persist_document_batch

    document_id = persist_document_batch(file.filename, raw_text, len(bugs), results)

    return {
        "document_id": document_id,
        "bug_count": len(bugs),
        "results": response_results
    }


@app.get("/documents/{id}")
def get_document(id: int) -> dict[str, Any]:
    """Fetch an uploaded document and all its verdicts."""
    try:
        from backend.db import get_document_with_verdicts
    except ModuleNotFoundError:
        from db import get_document_with_verdicts

    doc = get_document_with_verdicts(id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document with ID {id} not found")
    return doc

