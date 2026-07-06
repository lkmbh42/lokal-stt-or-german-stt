"""SQLite job store.

Single-user tool: short-lived connections per operation keep this trivially
thread-safe (job worker thread + request handlers) without a connection pool.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "processing", "done", "error", "canceled"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    duration REAL,
    options_json TEXT NOT NULL DEFAULT '{}',
    audio_path TEXT,
    transcript_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source: Literal["upload", "live"] = "upload"
    original_filename: str
    status: JobStatus = "queued"
    progress: float = 0.0
    error: str | None = None
    created_at: str = Field(default_factory=utcnow)
    started_at: str | None = None
    finished_at: str | None = None
    duration: float | None = None
    options_json: str = "{}"
    audio_path: str | None = None
    transcript_path: str | None = None

    @property
    def options(self) -> dict[str, Any]:
        return dict(json.loads(self.options_json))


class JobStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def add(self, record: JobRecord) -> JobRecord:
        data = record.model_dump()
        columns = ", ".join(data)
        placeholders = ", ".join(f":{k}" for k in data)
        with self._connect() as conn:
            conn.execute(f"INSERT INTO jobs ({columns}) VALUES ({placeholders})", data)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return JobRecord(**dict(row)) if row else None

    def list(self) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [JobRecord(**dict(row)) for row in rows]

    def update(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = :job_id",
                {**fields, "job_id": job_id},
            )

    def delete(self, job_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cur.rowcount > 0
