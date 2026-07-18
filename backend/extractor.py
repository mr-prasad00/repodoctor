"""Extract reproducible bug claims using Gemini or OpenAI JSON mode."""

from __future__ import annotations

import json
import os
from typing import Any, TypedDict

try:
    from openai import OpenAI
except ImportError:  # Allows the rest of the backend to load before dependencies exist.
    OpenAI = None  # type: ignore[assignment,misc]

try:
    from google import genai
    from google.genai import types as gemini_types
except ImportError:  # Allows the rest of the backend to load before dependencies exist.
    genai = None  # type: ignore[assignment,misc]
    gemini_types = None  # type: ignore[assignment,misc]


SYSTEM_PROMPT = """You extract a reproducible bug claim from an issue. Return ONLY JSON:
{
  "function": str|null,
  "inputs": list|null,
  "expected": any|null,
  "observed": any|null,
  "version": str|null,
  "confidence": number|null
}
If a field is not clearly stated, set it to null. Never invent values.
"""


class Extraction(TypedDict):
    function: str | None
    inputs: list[Any] | None
    expected: Any | None
    observed: Any | None
    version: str | None
    confidence: float | None


def extract(title: str, body: str, provider: str | None = None) -> Extraction:
    """Extract a structured reproduction claim from an issue title and body."""
    resolved_provider = _resolve_provider(provider)
    prompt = f"{SYSTEM_PROMPT}\nTitle: {title}\n\nBody: {body}"

    if resolved_provider == "gemini":
        content = _extract_with_gemini(prompt)
    elif resolved_provider == "openai":
        content = _extract_with_openai(title, body)
    elif resolved_provider == "grok":
        content = _extract_with_grok(title, body)
    else:
        raise ValueError(f"Unsupported AI provider: {resolved_provider}")

    if not content:
        raise ValueError(f"{resolved_provider.title()} returned an empty extraction response.")

    cleaned = _extract_json_string(content)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError(f"{resolved_provider.title()} extraction response must be a JSON object.")

    return _normalise(parsed)


def _resolve_provider(requested: str | None = None) -> str:
    """Resolve which AI provider to use, with auto-detection priority (Gemini -> OpenAI -> Grok)."""
    # 1. Check if a specific, configured provider is requested via function call argument
    if requested:
        req = requested.lower()
        if req == "gemini" and os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") not in ("your_gemini_api_key", "]"):
            return "gemini"
        if req == "openai" and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_KEY") != "your_openai_api_key":
            return "openai"
        if req == "grok" and (os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")) and (os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")) != "your_grok_api_key":
            return "grok"

    # 2. Check if there is an explicit environmental override (like AI_PROVIDER)
    configured = os.getenv("AI_PROVIDER")
    if configured:
        return configured.lower()

    # 3. Auto-detection priority
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key not in ("your_gemini_api_key", "", None, "]"):
        return "gemini"

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key not in ("your_openai_api_key", "", None):
        return "openai"

    grok_key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
    if grok_key and grok_key not in ("your_grok_api_key", "", None):
        return "grok"

    return "gemini"


def _extract_with_gemini(prompt: str) -> str | None:
    if genai is None or gemini_types is None:
        raise RuntimeError("The google-genai package is required for Gemini extraction.")

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


def _extract_with_openai(title: str, body: str) -> str | None:
    if OpenAI is None:
        raise RuntimeError("The openai package is required for OpenAI extraction.")

    client = OpenAI()
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Title: {title}\n\nBody: {body}"},
        ],
    )
    return response.choices[0].message.content


def _extract_with_grok(title: str, body: str) -> str | None:
    if OpenAI is None:
        raise RuntimeError("The openai package is required for Grok extraction.")

    api_key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY or XAI_API_KEY is required for Grok extraction.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )
    response = client.chat.completions.create(
        model=os.getenv("GROK_MODEL", "grok-2-1212"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Title: {title}\n\nBody: {body}"},
        ],
    )
    return response.choices[0].message.content


def _normalise(data: dict[str, Any]) -> Extraction:
    """Keep the extraction contract stable without filling in missing evidence."""
    function = data.get("function")
    inputs = data.get("inputs")
    version = data.get("version")
    confidence = data.get("confidence")

    return {
        "function": function.strip() if isinstance(function, str) and function.strip() else None,
        "inputs": inputs if isinstance(inputs, list) else None,
        "expected": data.get("expected"),
        "observed": data.get("observed"),
        "version": version.strip() if isinstance(version, str) and version.strip() else None,
        "confidence": float(confidence)
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= confidence <= 1
        else None,
    }


def _extract_json_string(text: str) -> str:
    """Find and return the outermost JSON object substring within the text."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start:end+1]
