"""Offline coverage for the RepoDoctor MVP pipeline.

OpenAI and Docker are replaced with local fakes so this suite never needs a key,
network access, or a running container daemon.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.extractor as extractor
import backend.main as main
import backend.sandbox as sandbox
from backend.test_generator import generate_test, validate_test_source
from backend.verdict import decide_verdict
from target_repo.calculator import divide, get_discount


EXTRACTED_DISCOUNT = {
    "function": "get_discount",
    "inputs": [100, 20],
    "expected": 80,
    "observed": 120,
    "version": None,
    "confidence": 0.9,
}


def test_calculator_demo_functions() -> None:
    assert get_discount(100, 20) == 120
    assert divide(10, 2) == 5


def test_extractor_parses_a_mocked_json_mode_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(EXTRACTED_DISCOUNT)))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setattr(extractor, "OpenAI", lambda: fake_client)

    assert extractor.extract("discount", "wrong result") == EXTRACTED_DISCOUNT


def test_extractor_parses_a_mocked_gemini_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(text=json.dumps(EXTRACTED_DISCOUNT))
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **_: response)
    )
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(extractor, "genai", SimpleNamespace(Client=lambda **_: fake_client))
    monkeypatch.setattr(
        extractor,
        "gemini_types",
        SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs),
    )

    assert extractor.extract("discount", "wrong result") == EXTRACTED_DISCOUNT


def test_gemini_default_model_uses_supported_value(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(text=json.dumps(EXTRACTED_DISCOUNT))
    captured: dict[str, Any] = {}

    class FakeModels:
        def generate_content(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return response

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.models = FakeModels()

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(extractor, "genai", SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr(
        extractor,
        "gemini_types",
        SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs),
    )

    assert extractor.extract("discount", "wrong result") == EXTRACTED_DISCOUNT
    assert captured["model"] == "gemini-2.0-flash"


def test_test_generator_generates_and_validates_one_target_repo_test() -> None:
    source = generate_test(EXTRACTED_DISCOUNT)

    assert "from target_repo.calculator import get_discount" in source
    assert "assert get_discount(100, 20) == 80" in source
    validate_test_source(source)


def test_test_generator_rejects_invalid_test_source() -> None:
    with pytest.raises(ValueError, match="import from target_repo"):
        validate_test_source("def test_repro():\n    assert True\n")

    with pytest.raises(ValueError, match="exactly one"):
        validate_test_source(
            "from target_repo.calculator import divide\n\n"
            "def test_one():\n    assert divide(10, 2) == 5\n\n"
            "def test_two():\n    assert divide(10, 2) == 5\n"
        )


def test_sandbox_uses_required_docker_security_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *_, **__: completed)

    result = sandbox.run_test("def test_repro():\n    assert True\n")

    assert result == {"passed": True, "output": "1 passed\n", "timed_out": False, "exit_code": 0}


def test_sandbox_marks_a_timeout_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    timeout = subprocess.TimeoutExpired("docker", 10, output="partial output")
    calls = []

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(args[0])
        if len(calls) == 1:
            raise timeout
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)

    result = sandbox.run_test("def test_repro():\n    assert True\n")

    assert result == {"passed": False, "output": "partial output", "timed_out": True, "exit_code": -1}
    command = calls[0]
    assert "--network" in command and command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert "--cpus=1" in command
    assert "--memory=256m" in command


@pytest.mark.parametrize(
    ("sandbox_result", "expected"),
    [
        ({"passed": False, "output": "assertion failed", "timed_out": False}, "reproduced"),
        ({"passed": True, "output": "1 passed", "timed_out": False}, "not_reproducible"),
        ({"passed": False, "output": "", "timed_out": True}, "insufficient_info"),
    ],
)
def test_verdict_mapping(sandbox_result: dict[str, object], expected: str) -> None:
    assert decide_verdict(sandbox_result) == expected


@pytest.mark.parametrize(
    ("extracted", "sandbox_result", "expected_status"),
    [
        (EXTRACTED_DISCOUNT, {"passed": False, "output": "assertion failed", "timed_out": False}, "reproduced"),
        (
            {**EXTRACTED_DISCOUNT, "function": "divide", "expected": 5, "observed": 5},
            {"passed": True, "output": "1 passed", "timed_out": False},
            "not_reproducible",
        ),
        ({**EXTRACTED_DISCOUNT, "inputs": None}, None, "insufficient_info"),
    ],
)
def test_analyze_response_shape_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extracted: dict[str, object],
    sandbox_result: dict[str, object] | None,
    expected_status: str,
) -> None:
    database_path = tmp_path / "repodoctor.db"
    monkeypatch.setenv("REPODOCTOR_DB_PATH", str(database_path))
    monkeypatch.setattr(main, "extract", lambda _title, _body, *args, **kwargs: extracted)
    monkeypatch.setattr(main, "run_test", lambda _source: sandbox_result)

    with TestClient(main.app) as client:
        response = client.post("/analyze", json={"title": "demo", "body": "demo body"})

    assert response.status_code == 200
    assert set(response.json()) == {
        "status",
        "extracted",
        "generated_test",
        "run_output",
        "explanation",
        "duration_ms",
    }
    assert response.json()["status"] == expected_status

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1
        assert connection.execute("SELECT status FROM verdicts").fetchone()[0] == expected_status


def test_analyze_rejects_blank_input_offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REPODOCTOR_DB_PATH", str(tmp_path / "repodoctor.db"))
    with TestClient(main.app) as client:
        response = client.post("/analyze", json={"title": " ", "body": "body"})

    assert response.status_code == 422


def test_grok_provider_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROK_API_KEY", "fake_grok_key")
    monkeypatch.setenv("GROK_MODEL", "grok-2-1212")

    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "function": "get_discount",
                            "inputs": [100, 20],
                            "expected": 80,
                            "observed": 120,
                            "version": "1.0.0",
                            "confidence": 0.95,
                        }
                    )
                )
            )
        ]
    )

    class FakeChat:
        def create(self, **kwargs: Any) -> Any:
            assert kwargs["model"] == "grok-2-1212"
            return fake_response

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["api_key"] == "fake_grok_key"
            assert kwargs["base_url"] == "https://api.x.ai/v1"
            self.chat = SimpleNamespace(completions=FakeChat())

    monkeypatch.setattr(extractor, "OpenAI", FakeClient)

    # Resolve provider requesting grok
    assert extractor._resolve_provider("grok") == "grok"

    # Test extraction with grok
    res = extractor.extract("discount", "wrong result", provider="grok")
    assert res["function"] == "get_discount"
    assert res["inputs"] == [100, 20]
    assert res["expected"] == 80


def test_providers_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai_key")
    monkeypatch.setenv("GROQ_API_KEY", "groq_key")
    monkeypatch.setenv("GROK_API_KEY", "grok_key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter_key")

    with TestClient(main.app) as client:
        response = client.get("/providers")

    assert response.status_code == 200
    data = response.json()
    assert data["providers"]["gemini"] is True
    assert data["providers"]["openai"] is True
    assert data["providers"]["groq"] is True
    assert data["providers"]["grok"] is True
    assert data["providers"]["openrouter"] is True
    assert data["default"] == "gemini"


def test_openrouter_provider_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake_openrouter_key")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "function": "split_payment",
                            "inputs": [100, 3],
                            "expected": [33, 33, 33],
                            "version": "1.0.0",
                            "confidence": 0.95,
                        }
                    )
                )
            )
        ]
    )

    class FakeChat:
        def create(self, **kwargs: Any) -> Any:
            assert kwargs["model"] == "meta-llama/llama-3.3-70b-instruct:free"
            return fake_response

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["api_key"] == "fake_openrouter_key"
            assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
            assert kwargs["default_headers"] == {
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "RepoDoctor",
            }
            self.chat = SimpleNamespace(completions=FakeChat())
            self.default_headers = kwargs["default_headers"]

    monkeypatch.setattr(extractor, "OpenAI", FakeClient)

    # Resolve provider requesting openrouter
    assert extractor._resolve_provider("openrouter") == "openrouter"

    # Test extraction with openrouter
    res = extractor.extract("split payment", "wrong result", provider="openrouter")
    assert res["function"] == "split_payment"
    assert res["inputs"] == [100, 3]
    assert res["expected"] == [33, 33, 33]


def test_generator_module_lookup_and_exceptions() -> None:
    from backend.test_generator import generate_test

    # Test dynamic module lookup for a function defined in billing.py
    billing_test = generate_test(
        {"function": "split_payment", "inputs": [100, 3], "expected": [33, 33, 33]}
    )
    assert "from target_repo.billing import split_payment" in billing_test
    assert "assert split_payment(100, 3) == [33, 33, 33]" in billing_test

    # Test dynamic module lookup for a function defined in calculator.py
    calculator_test = generate_test(
        {"function": "get_discount", "inputs": [100, 20], "expected": 80}
    )
    assert "from target_repo.calculator import get_discount" in calculator_test
    assert "assert get_discount(100, 20) == 80" in calculator_test

    # Test exception test generation using pytest.raises
    exception_test = generate_test(
        {"function": "cart_total", "inputs": [50, -2], "expected": "ValueError"}
    )
    assert "import pytest" in exception_test
    assert "from target_repo.billing import cart_total" in exception_test
    assert "with pytest.raises(ValueError):" in exception_test
    assert "cart_total(50, -2)" in exception_test


def test_groq_key_autodetect_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROK_API_KEY", "gsk_fake_groq_key")
    monkeypatch.setenv("GROK_MODEL", "llama-3.3-70b-versatile")

    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "function": "split_payment",
                            "inputs": [100, 3],
                            "expected": [33, 33, 33],
                            "version": "1.0.0",
                            "confidence": 0.95,
                        }
                    )
                )
            )
        ]
    )

    class FakeChat:
        def create(self, **kwargs: Any) -> Any:
            assert kwargs["model"] == "llama-3.3-70b-versatile"
            return fake_response

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["api_key"] == "gsk_fake_groq_key"
            assert kwargs["base_url"] == "https://api.groq.com/openai/v1"
            self.chat = SimpleNamespace(completions=FakeChat())

    monkeypatch.setattr(extractor, "OpenAI", FakeClient)

    # Test extraction with groq key under grok provider
    res = extractor.extract("split payment", "wrong result", provider="grok")
    assert res["function"] == "split_payment"
    assert res["inputs"] == [100, 3]
    assert res["expected"] == [33, 33, 33]


def test_groq_provider_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "function": "split_payment",
                            "inputs": [100, 3],
                            "expected": [33, 33, 33],
                            "version": "1.0.0",
                            "confidence": 0.95,
                        }
                    )
                )
            )
        ]
    )

    class FakeChat:
        def create(self, **kwargs: Any) -> Any:
            assert kwargs["model"] == "llama-3.3-70b-versatile"
            assert kwargs["response_format"] == {"type": "json_object"}
            return fake_response

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["api_key"] == "fake_groq_key"
            assert kwargs["base_url"] == "https://api.groq.com/openai/v1"
            self.chat = SimpleNamespace(completions=FakeChat())

    monkeypatch.setattr(extractor, "OpenAI", FakeClient)

    # Resolve provider requesting groq
    assert extractor._resolve_provider("groq") == "groq"

    # Test extraction with groq
    res = extractor.extract("split payment", "wrong result", provider="groq")
    assert res["function"] == "split_payment"
    assert res["inputs"] == [100, 3]
    assert res["expected"] == [33, 33, 33]


def test_format_test_output_assertion_error() -> None:
    from backend.sandbox import format_test_output

    raw_output = """
    def test_repro():
>       assert add_loyalty_points(2147483647, 1) == 2147483648
E       assert -1 == 2147483648
E        +  where -1 = add_loyalty_points(2147483647, 1)
    """
    formatted = format_test_output(raw_output)
    assert "❌ TEST FAILURE ENCOUNTERED IN SANDBOX" in formatted
    assert "Executed:  add_loyalty_points(2147483647, 1)" in formatted
    assert "Returned:  -1" in formatted
    assert "Expected:  2147483648" in formatted


def test_format_test_output_runtime_error() -> None:
    from backend.sandbox import format_test_output

    raw_output = """
>   billing_test = split_payment(100, 3)
E   NameError: name 'split_payment' is not defined
    """
    formatted = format_test_output(raw_output)
    assert "❌ RUNTIME ERROR ENCOUNTERED IN SANDBOX" in formatted
    assert "Error Type: NameError" in formatted
    assert "Message:    name 'split_payment' is not defined" in formatted


def test_parse_document_text() -> None:
    from backend.parser import parse_document
    raw = b"Hello world # Title\nSome content"
    assert parse_document(raw, "doc.txt") == "Hello world # Title\nSome content"
    assert parse_document(raw, "doc.md") == "Hello world # Title\nSome content"


def test_split_document_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.splitter import split_document
    
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake_key")
    
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps([
                        {"title": "Bug 1", "body": "Body 1"},
                        {"title": "Bug 2", "body": "Body 2"}
                    ])
                )
            )
        ]
    )

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass
        chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: fake_response
            )
        )

    import backend.splitter as splitter
    monkeypatch.setattr(splitter, "OpenAI", FakeClient)

    res = split_document("some raw text", provider="openai")
    assert len(res) == 2
    assert res[0]["title"] == "Bug 1"
    assert res[0]["body"] == "Body 1"


def test_analyze_document_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from backend.models import AnalysisResult
    database_path = tmp_path / "repodoctor.db"
    monkeypatch.setenv("REPODOCTOR_DB_PATH", str(database_path))
    
    import backend.parser as parser
    import backend.splitter as splitter
    monkeypatch.setattr(parser, "parse_document", lambda _bytes, _name: "mocked document text")
    monkeypatch.setattr(splitter, "split_document", lambda _text, _prov: [
        {"title": "Bug A", "body": "Body A"},
        {"title": "Bug B", "body": "Body B"}
    ])
    
    mocked_result_1 = AnalysisResult(
        status="reproduced",
        extracted={"function": "func1", "inputs": [], "expected": 1, "observed": 2, "version": None, "confidence": 0.9},
        generated_test="def test_repro(): pass",
        run_output="AssertionError",
        explanation="first bug explanation",
        duration_ms=120
    )
    mocked_result_2 = AnalysisResult(
        status="not_reproducible",
        extracted={"function": "func2", "inputs": [], "expected": 3, "observed": 3, "version": None, "confidence": 0.8},
        generated_test="def test_repro(): pass",
        run_output="Pass",
        explanation="second bug explanation",
        duration_ms=80
    )
    
    pipeline_calls = []
    def fake_run_pipeline(title: str, body: str, provider: str | None = None) -> AnalysisResult:
        pipeline_calls.append((title, body, provider))
        if len(pipeline_calls) == 1:
            return mocked_result_1
        return mocked_result_2

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    
    with TestClient(main.app) as client:
        files = {"file": ("document.md", b"my markdown file content")}
        response = client.post("/analyze-document", files=files, data={"provider": "groq"})
        
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["bug_count"] == 2
    assert "document_id" in res_data
    assert res_data["results"] == [
        {"seq": 1, "status": "reproduced", "explanation": "first bug explanation"},
        {"seq": 2, "status": "not_reproducible", "explanation": "second bug explanation"}
    ]
    
    assert len(pipeline_calls) == 2
    assert pipeline_calls[0] == ("Bug A", "Body A", "groq")
    assert pipeline_calls[1] == ("Bug B", "Body B", "groq")
    
    with sqlite3.connect(database_path) as connection:
        doc_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert doc_count == 1
        
        rep_rows = connection.execute("SELECT seq, issue_title, issue_body FROM reports").fetchall()
        assert len(rep_rows) == 2
        assert rep_rows[0] == (1, "Bug A", "Body A")
        assert rep_rows[1] == (2, "Bug B", "Body B")
        
        verdict_rows = connection.execute("SELECT status, explanation FROM verdicts").fetchall()
        assert len(verdict_rows) == 2
        assert verdict_rows[0] == ("reproduced", "first bug explanation")
        assert verdict_rows[1] == ("not_reproducible", "second bug explanation")

    doc_id = res_data["document_id"]
    with TestClient(main.app) as client:
        get_response = client.get(f"/documents/{doc_id}")
        
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert get_data["id"] == doc_id
    assert get_data["filename"] == "document.md"
    assert get_data["raw_text"] == "mocked document text"
    assert get_data["bug_count"] == 2
    assert len(get_data["reports"]) == 2
    assert get_data["reports"][0]["seq"] == 1
    assert get_data["reports"][0]["status"] == "reproduced"
    
    with TestClient(main.app) as client:
        get_404 = client.get("/documents/99999")
    assert get_404.status_code == 404
