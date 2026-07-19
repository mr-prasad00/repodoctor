"""Split a multi-bug document into structured individual reports using LLM splitting."""

from __future__ import annotations

import json
import os
import time
from typing import Any

try:
    from backend.extractor import _resolve_provider, _extract_json_string
except ModuleNotFoundError:
    from extractor import _resolve_provider, _extract_json_string

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]

try:
    from google import genai
    from google.genai import types as gemini_types
except ImportError:
    genai = None  # type: ignore[assignment,misc]
    gemini_types = None  # type: ignore[assignment,misc]

SPLITTER_SYSTEM_PROMPT = (
    "A document may describe multiple bugs. Split it into a JSON array, one object "
    "per distinct bug: [{\"title\": str, \"body\": str}]. If only one bug, return one item. "
    "Do not merge unrelated bugs. Do not invent bugs."
)


def split_document(raw_text: str, provider: str | None = None) -> list[dict[str, str]]:
    """Split a raw document text into a list of separate bug claims."""
    resolved_provider = _resolve_provider(provider)
    prompt = f"{SPLITTER_SYSTEM_PROMPT}\n\nUSER:\n{raw_text}"

    if resolved_provider == "gemini":
        content = _split_with_gemini(prompt)
    elif resolved_provider == "openai":
        content = _split_with_openai(raw_text)
    elif resolved_provider == "groq":
        content = _split_with_groq(raw_text)
    elif resolved_provider == "grok":
        content = _split_with_grok(raw_text)
    elif resolved_provider == "openrouter":
        content = _split_with_openrouter(raw_text)
    else:
        raise ValueError(f"Unsupported AI provider: {resolved_provider}")

    if not content:
        raise ValueError(f"{resolved_provider.title()} returned an empty splitter response.")

    cleaned = _extract_json_array_string(content)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        if isinstance(parsed, dict):
            return [parsed]  # type: ignore[list-item]
        raise ValueError(f"{resolved_provider.title()} splitter response must be a JSON array of objects.")

    validated = []
    for item in parsed:
        if isinstance(item, dict):
            title = str(item.get("title", "Untitled Bug")).strip()
            body = str(item.get("body", "")).strip()
            if title or body:
                validated.append({"title": title, "body": body})

    return validated


def _extract_json_array_string(text: str) -> str:
    """Find and return the outermost JSON array substring within the text."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return _extract_json_string(text)
    return text[start:end+1]


def _split_with_gemini(prompt: str) -> str | None:
    if genai is None or gemini_types is None:
        raise RuntimeError("The google-genai package is required for Gemini splitting.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required when AI_PROVIDER=gemini.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        contents=prompt,
        config=gemini_types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return response.text


def _split_with_openai(raw_text: str) -> str | None:
    if OpenAI is None:
        raise RuntimeError("The openai package is required for OpenAI splitting.")

    client = OpenAI()
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SPLITTER_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
    )
    return response.choices[0].message.content


def _split_with_groq(raw_text: str) -> str | None:
    if OpenAI is None:
        raise RuntimeError("The openai package is required for Groq splitting.")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for Groq splitting.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SPLITTER_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
    )
    return response.choices[0].message.content


def _split_with_grok(raw_text: str) -> str | None:
    if OpenAI is None:
        raise RuntimeError("The openai package is required for Grok splitting.")

    api_key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY or XAI_API_KEY is required for Grok splitting.")

    is_groq = api_key.startswith("gsk_")
    base_url = "https://api.groq.com/openai/v1" if is_groq else "https://api.x.ai/v1"

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    response = client.chat.completions.create(
        model=os.getenv("GROK_MODEL", "grok-2-1212"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SPLITTER_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
    )
    return response.choices[0].message.content


def _split_with_openrouter(raw_text: str) -> str | None:
    if OpenAI is None:
        raise RuntimeError("The openai package is required for OpenRouter splitting.")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter splitting.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "RepoDoctor",
        },
    )
    model_name = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SPLITTER_SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
            )
            return response.choices[0].message.content
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate" in err_msg.lower() or "limit" in err_msg.lower():
                if attempt < 2:
                    time.sleep(3)
                    continue
            raise e
    return None
