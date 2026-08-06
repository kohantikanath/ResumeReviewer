"""FastAPI application for batch resume verification."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from typing import Annotated

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import ADMIN_COOKIE, admin_configured, require_admin
from app.api.jobs import JobStatus, job_store, mark_stale_running_jobs
from app.bundle import extract_zip_bundle, resolve_pdfs_from_metadata
from app.report.exporter import export_report_csv_zip, export_report_xlsx
from app.form_csv import load_form_csv
from app.form_pipeline import process_form_csv_async
from app.rules.reasons import failures_to_json_records
from app.verify import verify_batch_async, verify_pdf_async

APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_ROOT / "static"
UPLOAD_ROOT = APP_ROOT.parent / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ResumeVerify", version="0.1.0")


@app.on_event("startup")
def _startup_mark_stale_jobs() -> None:
    mark_stale_running_jobs()


def _outcome_issues(outcome) -> list[dict[str, str]]:
    return failures_to_json_records(outcome.evaluation.results, outcome.doc)


def _resume_rel_path(work_dir: Path, pdf_path: Path) -> str:
    try:
        return pdf_path.resolve().relative_to(work_dir.resolve()).as_posix()
    except ValueError:
        return pdf_path.name


def _outcome_summary_entry(
    job_id: str, work_dir: Path, outcome, resume_api_prefix: str = "/api/jobs"
) -> dict:
    resume_file = _resume_rel_path(work_dir, outcome.path)
    return {
        "filename": outcome.filename,
        "roll_number": outcome.roll_number,
        "name": outcome.name,
        "verdict": outcome.evaluation.verdict.value,
        "failed_rules": outcome.evaluation.failed_rules(),
        "hard_fails": outcome.evaluation.hard_fail_count,
        "soft_flags": outcome.evaluation.soft_flag_count,
        "issues": _outcome_issues(outcome),
        "resume_file": resume_file,
        "resume_url": f"{resume_api_prefix}/{job_id}/resume/{resume_file}",
    }

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
    return RedirectResponse(url="/student", status_code=302)


@app.get("/student", response_class=HTMLResponse)
@app.get("/student/results/{job_id}", response_class=HTMLResponse)
async def spa_pages_student() -> HTMLResponse:
    return _index_html()


@app.get("/admin/login", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/history", response_class=HTMLResponse)
@app.get("/docs", response_class=HTMLResponse)
@app.get("/results", response_class=HTMLResponse)
@app.get("/results/{job_id}", response_class=HTMLResponse)
async def spa_pages_admin() -> HTMLResponse:
    return _index_html()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/admin/session")
async def admin_session(
    rv_admin: Annotated[str | None, Cookie(alias=ADMIN_COOKIE)] = None,
) -> dict[str, bool]:
    authenticated = not admin_configured() or rv_admin == "ok"
    return {"authenticated": authenticated, "password_required": admin_configured()}


@app.post("/api/admin/login")
async def admin_login(password: str = Form(...)) -> JSONResponse:
    if not admin_configured():
        response = JSONResponse({"ok": True, "message": "No admin password configured"})
        response.set_cookie(ADMIN_COOKIE, "ok", httponly=True, samesite="lax")
        return response
    if password != os.environ.get("RESUMEVERIFY_ADMIN_PASSWORD", ""):
        raise HTTPException(status_code=403, detail="Invalid password")
    response = JSONResponse({"ok": True})
    response.set_cookie(
        ADMIN_COOKIE,
        "ok",
        httponly=True,
        samesite="lax",
        max_age=86400 * 30,
    )
    return response


@app.post("/api/admin/logout")
async def admin_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(ADMIN_COOKIE)
    return response


async def _run_student_job(
    job_id: str,
    pdf_path: Path,
    work_dir: Path,
    check_links: bool,
) -> None:
    job_store.update(job_id, status=JobStatus.RUNNING, phase="rules", work_dir=work_dir)
    try:
        outcome = await verify_pdf_async(
            pdf_path,
            metadata=None,
            check_links=check_links,
            student_self_check=True,
        )
        summary_entry = _outcome_summary_entry(
            job_id, work_dir, outcome, resume_api_prefix="/api/student/jobs"
        )
        job_store.update(
            job_id,
            processed=1,
            phase="done",
            outcomes_summary=[summary_entry],
            status=JobStatus.COMPLETED,
        )
    except Exception as exc:
        job_store.update(
            job_id,
            status=JobStatus.FAILED,
            phase="error",
            error=str(exc),
        )


@app.post("/api/student/verify")
async def student_verify(
    background_tasks: BackgroundTasks,
    resume: UploadFile = File(...),
    check_links: bool = Query(True),
) -> dict:
    if not resume.filename or not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF resume")

    work_dir = Path(tempfile.mkdtemp(prefix="rv_student_", dir=UPLOAD_ROOT))
    dest = work_dir / resume.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(resume.file, f)

    job = job_store.create(total=1, method="student")
    background_tasks.add_task(
        _run_student_job,
        job.id,
        dest,
        work_dir,
        check_links,
    )
    return {"job_id": job.id, "total": 1, "status": job.status.value}


@app.get("/api/student/jobs/{job_id}")
async def get_student_job(job_id: str) -> dict:
    job = job_store.get(job_id)
    if not job or job.method != "student":
        raise HTTPException(status_code=404, detail="Job not found")
    data = job.to_dict()
    if data.get("outcomes_summary"):
        for entry in data["outcomes_summary"]:
            entry["resume_url"] = (
                f"/api/student/jobs/{job_id}/resume/{entry.get('resume_file', '')}"
            )
    return data


@app.get("/api/student/jobs/{job_id}/resume/{resume_path:path}")
async def download_student_resume(job_id: str, resume_path: str) -> FileResponse:
    job = job_store.get(job_id)
    if not job or job.method != "student" or not job.work_dir:
        raise HTTPException(status_code=404, detail="Job not found")
    base = Path(job.work_dir).resolve()
    target = (base / resume_path).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(status_code=404, detail="Resume PDF not found")
    return FileResponse(
        target,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{target.name}"'},
    )


async def _run_batch_job(
    job_id: str,
    pdf_paths: list[Path],
    metadata_path: Path | None,
    work_dir: Path,
    check_links: bool,
) -> None:
    job_store.update(job_id, status=JobStatus.RUNNING, phase="prepare", work_dir=work_dir)

    partial_summary: list[dict] = []

    def on_progress(processed: int, total: int, phase: str) -> None:
        job_store.update(job_id, processed=processed, phase=phase)

    def on_outcome(outcome, processed: int, total: int) -> None:
        partial_summary.append(_outcome_summary_entry(job_id, work_dir, outcome))
        job_store.update(
            job_id,
            processed=processed,
            phase="rules",
            outcomes_summary=list(partial_summary),
        )

    try:
        outcomes = await verify_batch_async(
            pdf_paths,
            metadata_path=metadata_path,
            check_links=check_links,
            progress_callback=on_progress,
            outcome_callback=on_outcome,
        )

        job_store.update(job_id, phase="report")
        report_path = work_dir / "results.xlsx"
        export_report_xlsx(outcomes, report_path)
        export_report_csv_zip(outcomes, work_dir / "results_csv.zip")

        summary = [
            _outcome_summary_entry(job_id, work_dir, o) for o in outcomes
        ]

        job_store.update(
            job_id,
            status=JobStatus.COMPLETED,
            processed=len(outcomes),
            phase="done",
            report_path=report_path,
            report_csv_zip_path=work_dir / "results_csv.zip",
            work_dir=work_dir,
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
    job_store.update(job_id, status=JobStatus.RUNNING, phase="download", work_dir=work_dir)

    partial_summary: list[dict] = []

    def on_progress(processed: int, total: int, phase: str) -> None:
        job_store.update(job_id, processed=processed, phase=phase)

    def on_outcome(outcome, processed: int, total: int) -> None:
        partial_summary.append(_outcome_summary_entry(job_id, work_dir, outcome))
        job_store.update(
            job_id,
            processed=processed,
            phase="rules",
            outcomes_summary=list(partial_summary),
        )

    try:
        outcomes, report_path, csv_zip = await process_form_csv_async(
            csv_path,
            work_dir,
            check_links=check_links,
            progress_callback=on_progress,
            outcome_callback=on_outcome,
        )
        summary = [
            _outcome_summary_entry(job_id, work_dir, o) for o in outcomes
        ]
        job_store.update(
            job_id,
            status=JobStatus.COMPLETED,
            processed=len(outcomes),
            phase="done",
            report_path=report_path,
            report_csv_zip_path=csv_zip,
            work_dir=work_dir,
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
    _: None = Depends(require_admin),
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
        "total": job.total,
        "status": job.status.value,
        "message": "Downloading and verifying each resume one by one",
    }


@app.post("/api/batch")
async def create_batch(
    background_tasks: BackgroundTasks,
    bundle: UploadFile | None = File(None),
    resumes: Annotated[list[UploadFile], File()] = [],
    metadata: UploadFile | None = File(None),
    check_links: bool = Query(True),
    _: None = Depends(require_admin),
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
async def clear_jobs(_: None = Depends(require_admin)) -> dict[str, int | str]:
    """Remove all jobs from memory/disk and delete old batch work folders."""
    job_store.clear_all()
    removed = 0
    for child in UPLOAD_ROOT.iterdir():
        if child.is_dir() and child.name.startswith("rv_"):
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return {"status": "ok", "removed_workdirs": removed}


@app.get("/api/jobs")
async def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    _: None = Depends(require_admin),
) -> dict:
    jobs = [j for j in job_store.list_recent(limit * 2) if j.method != "student"][:limit]
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
async def get_job(job_id: str, _: None = Depends(require_admin)) -> dict:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/resume/{resume_path:path}")
async def download_resume_pdf(
    job_id: str,
    resume_path: str,
    _: None = Depends(require_admin),
) -> FileResponse:
    job = job_store.get(job_id)
    if not job or not job.work_dir:
        raise HTTPException(status_code=404, detail="Job not found")
    base = Path(job.work_dir).resolve()
    target = (base / resume_path).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=403, detail="Invalid path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Resume PDF not found")
    return FileResponse(
        target,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{target.name}"'},
    )


@app.get("/api/jobs/{job_id}/report")
async def download_report(
    job_id: str,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    _: None = Depends(require_admin),
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
