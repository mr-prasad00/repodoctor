"""SQLite storage for submitted reports and their verdicts."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

try:
    from backend.models import AnalysisResult, PersistedReport
except ModuleNotFoundError:
    from models import AnalysisResult, PersistedReport


DEFAULT_DATABASE_PATH = Path(__file__).with_name("repodoctor.db")


def get_connection() -> sqlite3.Connection:
    """Open a database connection with foreign-key checks enabled."""
    database_path = Path(os.getenv("REPODOCTOR_DB_PATH", DEFAULT_DATABASE_PATH))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    """Create the MVP database tables and indexes when they do not yet exist."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                raw_text TEXT NOT NULL,
                bug_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER REFERENCES documents(id),
                seq INTEGER,
                issue_title TEXT NOT NULL,
                issue_body TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS verdicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL REFERENCES reports(id),
                status TEXT NOT NULL,
                extracted_json TEXT,
                generated_test TEXT,
                run_output TEXT,
                explanation TEXT,
                duration_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_reports_document ON reports(document_id);
            CREATE INDEX IF NOT EXISTS idx_verdicts_report ON verdicts(report_id);
            CREATE INDEX IF NOT EXISTS idx_verdicts_status ON verdicts(status);
            """
        )


def persist_analysis(title: str, body: str, result: AnalysisResult) -> PersistedReport:
    """Store one pasted report as a document, report, and verdict record."""
    init_db()
    with get_connection() as connection:
        document_cursor = connection.execute(
            "INSERT INTO documents (filename, raw_text, bug_count) VALUES (?, ?, ?)",
            (None, f"{title}\n\n{body}", 1),
        )
        document_id = int(document_cursor.lastrowid)
        report_cursor = connection.execute(
            """
            INSERT INTO reports (document_id, seq, issue_title, issue_body)
            VALUES (?, ?, ?, ?)
            """,
            (document_id, 1, title, body),
        )
        report_id = int(report_cursor.lastrowid)
        verdict_cursor = connection.execute(
            """
            INSERT INTO verdicts (
                report_id, status, extracted_json, generated_test, run_output,
                explanation, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                result.status,
                json.dumps(result.extracted) if result.extracted is not None else None,
                result.generated_test,
                result.run_output,
                result.explanation,
                result.duration_ms,
            ),
        )
        return PersistedReport(document_id, report_id, int(verdict_cursor.lastrowid))


def persist_document_batch(
    filename: str | None,
    raw_text: str,
    bug_count: int,
    results: list[tuple[str, str, AnalysisResult]]
) -> int:
    """Store an uploaded/parsed document, its split reports, and their verdicts."""
    init_db()
    with get_connection() as connection:
        document_cursor = connection.execute(
            "INSERT INTO documents (filename, raw_text, bug_count) VALUES (?, ?, ?)",
            (filename, raw_text, bug_count),
        )
        document_id = int(document_cursor.lastrowid)

        for seq, (title, body, result) in enumerate(results, start=1):
            report_cursor = connection.execute(
                """
                INSERT INTO reports (document_id, seq, issue_title, issue_body)
                VALUES (?, ?, ?, ?)
                """,
                (document_id, seq, title, body),
            )
            report_id = int(report_cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO verdicts (
                    report_id, status, extracted_json, generated_test, run_output,
                    explanation, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    result.status,
                    json.dumps(result.extracted) if result.extracted is not None else None,
                    result.generated_test,
                    result.run_output,
                    result.explanation,
                    result.duration_ms,
                ),
            )
        return document_id


def get_document_with_verdicts(document_id: int) -> dict[str, Any] | None:
    """Retrieve a document and all its reports and verdicts."""
    init_db()
    with get_connection() as connection:
        connection.row_factory = sqlite3.Row
        doc_row = connection.execute(
            "SELECT id, filename, raw_text, bug_count, created_at FROM documents WHERE id = ?",
            (document_id,),
        )
        doc = doc_row.fetchone()
        if not doc:
            return None

        reports_cursor = connection.execute(
            """
            SELECT 
                r.id as report_id, r.seq, r.issue_title, r.issue_body,
                v.status, v.extracted_json, v.generated_test, v.run_output,
                v.explanation, v.duration_ms
            FROM reports r
            LEFT JOIN verdicts v ON r.id = v.report_id
            WHERE r.document_id = ?
            ORDER BY r.seq ASC
            """,
            (document_id,),
        )
        reports = []
        for row in reports_cursor.fetchall():
            extracted_dict = None
            if row["extracted_json"]:
                try:
                    extracted_dict = json.loads(row["extracted_json"])
                except Exception:
                    pass
            reports.append({
                "seq": row["seq"],
                "issue_title": row["issue_title"],
                "issue_body": row["issue_body"],
                "status": row["status"],
                "extracted": extracted_dict,
                "generated_test": row["generated_test"],
                "run_output": row["run_output"],
                "explanation": row["explanation"],
                "duration_ms": row["duration_ms"],
            })

        return {
            "id": doc["id"],
            "filename": doc["filename"],
            "raw_text": doc["raw_text"],
            "bug_count": doc["bug_count"],
            "created_at": doc["created_at"],
            "reports": reports,
        }
