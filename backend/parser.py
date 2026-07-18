"""Document parser for raw text and PDF formats."""

from __future__ import annotations

import io
from pypdf import PdfReader


def parse_document(file_content: bytes, filename: str) -> str:
    """Extract raw text from a text, markdown, or PDF document."""
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    if ext == "pdf":
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)

    # Default to reading as plain text / markdown
    try:
        return file_content.decode("utf-8", errors="replace")
    except Exception:
        return ""
