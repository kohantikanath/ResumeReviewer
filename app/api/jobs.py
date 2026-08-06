"""In-memory job tracking for batch verification."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobRecord:
    id: str
    status: JobStatus
    total: int
    processed: int = 0
    phase: str = "queued"
    created_at: str = ""
    error: str = ""
    report_path: str = ""
    report_csv_zip_path: str = ""
    outcomes_summary: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "total": self.total,
            "processed": self.processed,
            "phase": self.phase,
            "created_at": self.created_at,
            "error": self.error,
            "report_ready": bool(self.report_path),
            "csv_report_ready": bool(self.report_csv_zip_path),
            "outcomes_summary": self.outcomes_summary,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()

    def create(self, total: int) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(
            id=job_id,
            status=JobStatus.QUEUED,
            total=total,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_recent(self, limit: int = 20) -> list[JobRecord]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
            return jobs[:limit]

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        processed: int | None = None,
        phase: str | None = None,
        error: str | None = None,
        report_path: Path | None = None,
        report_csv_zip_path: Path | None = None,
        outcomes_summary: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if status is not None:
                job.status = status
            if processed is not None:
                job.processed = processed
            if phase is not None:
                job.phase = phase
            if error is not None:
                job.error = error
            if report_path is not None:
                job.report_path = str(report_path)
            if report_csv_zip_path is not None:
                job.report_csv_zip_path = str(report_csv_zip_path)
            if outcomes_summary is not None:
                job.outcomes_summary = outcomes_summary


job_store = JobStore()
