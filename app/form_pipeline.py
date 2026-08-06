"""Process Google Forms CSV: download Drive resumes and verify."""

from __future__ import annotations

import asyncio

import httpx
from pathlib import Path

from app.drive import download_google_drive_pdf
from app.form_csv import (
    load_form_csv,
    metadata_dict_from_applications,
    save_metadata_for_applications,
)
from app.report.exporter import export_report_csv_zip, export_report_xlsx
from app.types import VerificationOutcome
from app.verify import verify_pdf_async


async def process_form_csv_async(
    csv_path: Path,
    work_dir: Path,
    check_links: bool = True,
    progress_callback=None,
    outcome_callback=None,
) -> tuple[list[VerificationOutcome], Path, Path]:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    applications = load_form_csv(csv_path)
    total = len(applications)
    metadata = metadata_dict_from_applications(applications)
    pdf_dir = work_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    url_cache: dict[str, tuple[int | None, str]] = {}
    vanity_cache: dict[str, tuple[int | None, str]] = {}
    outcomes: list[VerificationOutcome] = []
    ready_apps: list = []

    async with httpx.AsyncClient(
        timeout=60.0,
        headers={"User-Agent": "ResumeVerify/1.0"},
        follow_redirects=True,
    ) as client:
        for index, app in enumerate(applications):
            if progress_callback:
                progress_callback(index, total, "download")

            try:
                path = await download_google_drive_pdf(
                    app.resume_url,
                    pdf_dir,
                    client,
                    app.name or app.email or "resume",
                )
            except Exception:
                continue

            app.local_pdf = path
            ready_apps.append(app)

            if progress_callback:
                progress_callback(index, total, "links")

            outcome = await verify_pdf_async(
                path,
                metadata=metadata,
                check_links=check_links,
                url_cache=url_cache,
                vanity_cache=vanity_cache,
            )
            outcomes.append(outcome)
            processed = len(outcomes)
            if progress_callback:
                progress_callback(processed, total, "rules")
            if outcome_callback:
                outcome_callback(outcome, processed, total)

    if not outcomes:
        raise ValueError("No PDFs downloaded from Google Drive links.")

    metadata_path = save_metadata_for_applications(
        ready_apps, work_dir / "metadata.csv"
    )
    report_xlsx = work_dir / "results.xlsx"
    report_csv_zip = work_dir / "results_csv.zip"
    export_report_xlsx(outcomes, report_xlsx)
    export_report_csv_zip(outcomes, report_csv_zip)
    return outcomes, report_xlsx, report_csv_zip


def process_form_csv(
    csv_path: Path,
    work_dir: Path,
    check_links: bool = False,
) -> tuple[list[VerificationOutcome], Path, Path]:
    return asyncio.run(
        process_form_csv_async(csv_path, work_dir, check_links=check_links)
    )
