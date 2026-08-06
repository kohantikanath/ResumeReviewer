"""Job tracking for batch verification (memory + disk persistence)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any

_DEFAULT_INDEX = Path(__file__).resolve().parent.parent.parent / "uploads" / "job_index"


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
    work_dir: str = ""
    method: str = ""
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
            "method": self.method,
            "report_ready": bool(self.report_path),
            "csv_report_ready": bool(self.report_csv_zip_path),
            "outcomes_summary": self.outcomes_summary,
        }


class JobStore:
    def __init__(self, persist_dir: Path | None = None) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._persist_dir = persist_dir
        if self._persist_dir:
            self._persist_dir.mkdir(parents=True, exist_ok=True)

    def _persist_path(self, job_id: str) -> Path:
        assert self._persist_dir is not None
        return self._persist_dir / f"{job_id}.json"

    def _save(self, job: JobRecord) -> None:
        if not self._persist_dir:
            return
        payload = {
            "id": job.id,
            "status": job.status.value,
            "total": job.total,
            "processed": job.processed,
            "phase": job.phase,
            "created_at": job.created_at,
            "error": job.error,
            "report_path": job.report_path,
            "report_csv_zip_path": job.report_csv_zip_path,
            "work_dir": job.work_dir,
            "method": job.method,
            "outcomes_summary": job.outcomes_summary,
        }
        self._persist_path(job.id).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load(self, job_id: str) -> JobRecord | None:
        if not self._persist_dir:
            return None
        path = self._persist_path(job_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return JobRecord(
            id=data["id"],
            status=JobStatus(data["status"]),
            total=int(data["total"]),
            processed=int(data.get("processed", 0)),
            phase=str(data.get("phase", "")),
            created_at=str(data.get("created_at", "")),
            error=str(data.get("error", "")),
            report_path=str(data.get("report_path", "")),
            report_csv_zip_path=str(data.get("report_csv_zip_path", "")),
            work_dir=str(data.get("work_dir", "")),
            method=str(data.get("method", "")),
            outcomes_summary=list(data.get("outcomes_summary", [])),
        )

    def create(self, total: int, method: str = "") -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(
            id=job_id,
            status=JobStatus.QUEUED,
            total=total,
            method=method,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._jobs[job_id] = record
        self._save(record)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
        loaded = self._load(job_id)
        if loaded:
            with self._lock:
                self._jobs[job_id] = loaded
            return loaded
        return None

    def list_recent(self, limit: int = 20) -> list[JobRecord]:
        job_ids: set[str] = set()
        with self._lock:
            job_ids.update(self._jobs.keys())
        if self._persist_dir and self._persist_dir.exists():
            for path in self._persist_dir.glob("*.json"):
                job_ids.add(path.stem)

        jobs: list[JobRecord] = []
        for job_id in job_ids:
            job = self.get(job_id)
            if job:
                jobs.append(job)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
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
        work_dir: Path | None = None,
        outcomes_summary: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                job = self._load(job_id)
                if not job:
                    return
                self._jobs[job_id] = job
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
            if work_dir is not None:
                job.work_dir = str(work_dir)
            if outcomes_summary is not None:
                job.outcomes_summary = outcomes_summary
            self._save(job)

    def clear_all(self) -> None:
        with self._lock:
            self._jobs.clear()
        if self._persist_dir and self._persist_dir.exists():
            for path in self._persist_dir.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass


job_store = JobStore(persist_dir=_DEFAULT_INDEX)


def mark_stale_running_jobs() -> int:
    """After server restart, background workers are gone — don't leave zombie jobs."""
    marked = 0
    for job in job_store.list_recent(100):
        if job.status in (JobStatus.RUNNING, JobStatus.QUEUED):
            job_store.update(
                job.id,
                status=JobStatus.FAILED,
                phase="error",
                error=(
                    "Server restarted while this job was running. "
                    "Run verification again — any results already saved are still viewable below."
                ),
            )
            marked += 1
    return marked
