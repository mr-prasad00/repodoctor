"""Small data models used by RepoDoctor's SQLite persistence layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalysisResult:
    status: str
    extracted: dict[str, Any] | None
    generated_test: str | None
    run_output: str | None
    explanation: str
    duration_ms: int


@dataclass(frozen=True)
class PersistedReport:
    document_id: int
    report_id: int
    verdict_id: int
