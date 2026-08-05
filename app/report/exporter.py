"""Excel and CSV report export."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from app.links.validator import classify_url
from app.types import VerificationOutcome


def _build_frames(outcomes: list[VerificationOutcome]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    detail_rows = []
    link_rows = []

    for outcome in outcomes:
        ev = outcome.evaluation
        summary_rows.append(
            {
                "Roll No": outcome.roll_number,
                "Name": outcome.name,
                "Email": outcome.email,
                "Filename": outcome.filename,
                "Verdict": ev.verdict.value,
                "# Hard Fails": ev.hard_fail_count,
                "# Soft Flags": ev.soft_flag_count,
                "Reason Digest": ev.digest(),
            }
        )

        for result in ev.results:
            if result.passed:
                continue
            detail_rows.append(
                {
                    "Filename": outcome.filename,
                    "Roll No": outcome.roll_number,
                    "Name": outcome.name,
                    "Rule ID": result.rule_id,
                    "Severity": result.severity.value,
                    "Reason": result.reason,
                    "Evidence": result.evidence,
                }
            )

        for url, (status, note) in outcome.link_statuses.items():
            classification = classify_url(url, status, note)
            link_rows.append(
                {
                    "Filename": outcome.filename,
                    "Roll No": outcome.roll_number,
                    "URL": url,
                    "Status Code": status if status is not None else "",
                    "Note": note,
                    "Classification": classification,
                }
            )

    return (
        pd.DataFrame(summary_rows),
        pd.DataFrame(detail_rows),
        pd.DataFrame(link_rows),
    )


def export_report_xlsx(outcomes: list[VerificationOutcome], output_path: Path) -> Path:
    output_path = Path(output_path)
    summary, details, links = _build_frames(outcomes)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        details.to_excel(writer, sheet_name="Details", index=False)
        links.to_excel(writer, sheet_name="Link log", index=False)

    return output_path


def export_report_csv_bundle(outcomes: list[VerificationOutcome], output_dir: Path) -> Path:
    """Write summary.csv, details.csv, link_log.csv into a directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary, details, links = _build_frames(outcomes)
    summary.to_csv(output_dir / "summary.csv", index=False, encoding="utf-8-sig")
    details.to_csv(output_dir / "details.csv", index=False, encoding="utf-8-sig")
    links.to_csv(output_dir / "link_log.csv", index=False, encoding="utf-8-sig")
    return output_dir


def export_report_csv_zip(outcomes: list[VerificationOutcome], zip_path: Path) -> Path:
    """Zip the three CSV sheets for download."""
    zip_path = Path(zip_path)
    csv_dir = zip_path.parent / f"{zip_path.stem}_csv"
    export_report_csv_bundle(outcomes, csv_dir)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("summary.csv", "details.csv", "link_log.csv"):
            file_path = csv_dir / name
            if file_path.exists():
                zf.write(file_path, arcname=name)
    return zip_path
