"""Process Google Forms CSV: download Drive resumes and verify."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.form_csv import (
    download_form_resumes,
    load_form_csv,
    save_metadata_for_applications,
)
from app.report.exporter import export_report_csv_zip, export_report_xlsx
from app.types import VerificationOutcome
from app.verify import verify_batch_async


async def process_form_csv_async(
    csv_path: Path,
    work_dir: Path,
    check_links: bool = True,
    progress_callback=None,
) -> tuple[list[VerificationOutcome], Path, Path]:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    applications = load_form_csv(csv_path)
    applications = await download_form_resumes(applications, work_dir / "pdfs")

    metadata_path = save_metadata_for_applications(
        applications, work_dir / "metadata.csv"
    )
    pdf_paths = [app.local_pdf for app in applications if app.local_pdf]
    if not pdf_paths:
        raise ValueError("No PDFs downloaded from Google Drive links.")

    outcomes = await verify_batch_async(
        pdf_paths,
        metadata_path=metadata_path,
        check_links=check_links,
        progress_callback=progress_callback,
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
