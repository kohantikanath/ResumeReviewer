"""FastAPI application for batch resume verification."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.jobs import JobStatus, job_store
from app.bundle import extract_zip_bundle, resolve_pdfs_from_metadata
from app.report.exporter import export_report_csv_zip, export_report_xlsx
from app.form_csv import load_form_csv
from app.form_pipeline import process_form_csv_async
from app.rules.reasons import failures_to_json_records
from app.verify import verify_batch_async

APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_ROOT / "static"
UPLOAD_ROOT = APP_ROOT.parent / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ResumeVerify", version="0.1.0")


def _outcome_issues(outcome) -> list[dict[str, str]]:
    return failures_to_json_records(outcome.evaluation.results, outcome.doc)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _index_html() -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>ResumeVerify API</h1><p>Upload UI missing.</p>")
    return HTMLResponse(
        index_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/history", response_class=HTMLResponse)
@app.get("/docs", response_class=HTMLResponse)
@app.get("/results", response_class=HTMLResponse)
@app.get("/results/{job_id}", response_class=HTMLResponse)
async def spa_pages(job_id: str | None = None) -> HTMLResponse:
    return _index_html()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _run_batch_job(
    job_id: str,
    pdf_paths: list[Path],
    metadata_path: Path | None,
    work_dir: Path,
    check_links: bool,
) -> None:
    job_store.update(job_id, status=JobStatus.RUNNING, phase="extract")

    def on_progress(processed: int, total: int, phase: str) -> None:
        job_store.update(job_id, processed=processed, phase=phase)

    try:
        outcomes = await verify_batch_async(
            pdf_paths,
            metadata_path=metadata_path,
            check_links=check_links,
            progress_callback=on_progress,
        )

        report_path = work_dir / "results.xlsx"
        export_report_xlsx(outcomes, report_path)
        export_report_csv_zip(outcomes, work_dir / "results_csv.zip")

        summary = [
            {
                "filename": o.filename,
                "roll_number": o.roll_number,
                "name": o.name,
                "verdict": o.evaluation.verdict.value,
                "failed_rules": o.evaluation.failed_rules(),
                "hard_fails": o.evaluation.hard_fail_count,
                "soft_flags": o.evaluation.soft_flag_count,
                "issues": _outcome_issues(o),
            }
            for o in outcomes
        ]

        job_store.update(
            job_id,
            status=JobStatus.COMPLETED,
            processed=len(outcomes),
            phase="done",
            report_path=report_path,
            report_csv_zip_path=work_dir / "results_csv.zip",
            outcomes_summary=summary,
        )
    except Exception as exc:
        job_store.update(
            job_id,
            status=JobStatus.FAILED,
            phase="error",
            error=str(exc),
        )


async def _run_forms_csv_job(
    job_id: str,
    csv_path: Path,
    work_dir: Path,
    check_links: bool,
) -> None:
    job_store.update(job_id, status=JobStatus.RUNNING, phase="download")

    def on_progress(processed: int, total: int, phase: str) -> None:
        job_store.update(job_id, processed=processed, phase=phase)

    try:
        outcomes, report_path, csv_zip = await process_form_csv_async(
            csv_path,
            work_dir,
            check_links=check_links,
            progress_callback=on_progress,
        )
        summary = [
            {
                "filename": o.filename,
                "roll_number": o.roll_number,
                "name": o.name,
                "verdict": o.evaluation.verdict.value,
                "failed_rules": o.evaluation.failed_rules(),
                "hard_fails": o.evaluation.hard_fail_count,
                "soft_flags": o.evaluation.soft_flag_count,
                "issues": _outcome_issues(o),
            }
            for o in outcomes
        ]
        job_store.update(
            job_id,
            status=JobStatus.COMPLETED,
            processed=len(outcomes),
            phase="done",
            report_path=report_path,
            report_csv_zip_path=csv_zip,
            outcomes_summary=summary,
        )
    except Exception as exc:
        job_store.update(
            job_id,
            status=JobStatus.FAILED,
            phase="error",
            error=str(exc),
        )


@app.post("/api/batch/forms-csv")
async def create_batch_from_forms_csv(
    background_tasks: BackgroundTasks,
    form_csv: UploadFile = File(...),
    check_links: bool = Query(True),
) -> dict:
    """Google Forms CSV with Resume column containing Google Drive links."""
    if not form_csv.filename:
        raise HTTPException(status_code=400, detail="CSV file required")
    suffix = Path(form_csv.filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Upload a .csv or .xlsx Forms export")

    work_dir = Path(tempfile.mkdtemp(prefix="rv_forms_", dir=UPLOAD_ROOT))
    csv_path = work_dir / form_csv.filename
    with csv_path.open("wb") as f:
        shutil.copyfileobj(form_csv.file, f)

    try:
        applications = load_form_csv(csv_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = job_store.create(total=len(applications), method="forms")
    background_tasks.add_task(
        _run_forms_csv_job,
        job.id,
        csv_path,
        work_dir,
        check_links,
    )
    return {
        "job_id": job.id,
        "status": job.status.value,
        "message": "Downloading resumes from Google Drive, then verifying",
    }


@app.post("/api/batch")
async def create_batch(
    background_tasks: BackgroundTasks,
    bundle: UploadFile | None = File(None),
    resumes: Annotated[list[UploadFile], File()] = [],
    metadata: UploadFile | None = File(None),
    check_links: bool = Query(True),
) -> dict:
    work_dir = Path(tempfile.mkdtemp(prefix="rv_", dir=UPLOAD_ROOT))
    pdf_paths: list[Path] = []
    metadata_path: Path | None = None

    if bundle and bundle.filename:
        suffix = Path(bundle.filename).suffix.lower()
        if suffix != ".zip":
            raise HTTPException(
                status_code=400,
                detail="Bundle must be a .zip containing metadata.csv and PDF files",
            )
        zip_dest = work_dir / bundle.filename
        with zip_dest.open("wb") as f:
            shutil.copyfileobj(bundle.file, f)
        try:
            metadata_path, pdf_paths = extract_zip_bundle(zip_dest, work_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        if not resumes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Upload a ZIP containing metadata.csv + PDF files, "
                    "or upload PDF resumes directly."
                ),
            )

        for upload in resumes:
            if not upload.filename or not upload.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail=f"Invalid file: {upload.filename}")
            dest = work_dir / upload.filename
            with dest.open("wb") as f:
                shutil.copyfileobj(upload.file, f)
            pdf_paths.append(dest)

        if metadata and metadata.filename:
            metadata_path = work_dir / metadata.filename
            with metadata_path.open("wb") as f:
                shutil.copyfileobj(metadata.file, f)
            try:
                pdf_paths = resolve_pdfs_from_metadata(
                    metadata_path, work_dir, require_all=False
                )
            except ValueError as exc:
                if "no Filename" not in str(exc):
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not pdf_paths:
        raise HTTPException(status_code=400, detail="No PDF files to process")

    upload_method = "zip" if bundle and bundle.filename else "direct"
    job = job_store.create(total=len(pdf_paths), method=upload_method)
    background_tasks.add_task(
        _run_batch_job,
        job.id,
        pdf_paths,
        metadata_path,
        work_dir,
        check_links,
    )

    return {"job_id": job.id, "total": job.total, "status": job.status.value}


@app.post("/api/jobs/clear")
async def clear_jobs() -> dict[str, int | str]:
    """Remove all jobs from memory/disk and delete old batch work folders."""
    job_store.clear_all()
    removed = 0
    for child in UPLOAD_ROOT.iterdir():
        if child.is_dir() and child.name.startswith("rv_"):
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return {"status": "ok", "removed_workdirs": removed}


@app.get("/api/jobs")
async def list_jobs(limit: int = Query(20, ge=1, le=100)) -> dict:
    jobs = job_store.list_recent(limit)
    return {
        "jobs": [
            {
                "id": j.id,
                "status": j.status.value,
                "total": j.total,
                "processed": j.processed,
                "phase": j.phase,
                "created_at": j.created_at,
                "method": j.method,
                "report_ready": bool(j.report_path),
            }
            for j in jobs
        ]
    }


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/report")
async def download_report(
    job_id: str,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
) -> FileResponse:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Report not ready")

    if format == "csv":
        if not job.report_csv_zip_path:
            raise HTTPException(status_code=404, detail="CSV report missing")
        path = Path(job.report_csv_zip_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="CSV report file missing")
        return FileResponse(
            path,
            media_type="application/zip",
            filename="results_csv.zip",
        )

    if not job.report_path:
        raise HTTPException(status_code=400, detail="Report not ready")
    path = Path(job.report_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file missing")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="results.xlsx",
    )
