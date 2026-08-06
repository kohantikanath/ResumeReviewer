"""Google Forms / Sheets CSV with Google Drive resume links."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.config import ROLL_NUMBER_PATTERN
from app.drive import download_google_drive_pdfs, extract_google_drive_file_id
from app.metadata import COLUMN_ALIASES, _normalize_columns, _read_csv


RESUME_URL_ALIASES = {
    "resume": "Resume",
    "resume link": "Resume",
    "resume url": "Resume",
    "resume file": "Resume",
    "google drive": "Resume",
    "drive link": "Resume",
}


@dataclass
class FormApplication:
    name: str
    email: str
    contact: str
    scaler_cgpa: str
    bits_cgpa: str
    resume_url: str
    roll_number: str = ""
    timestamp: str = ""
    local_pdf: Path | None = None

    def metadata_record(self, filename: str) -> dict[str, str]:
        return {
            "Roll Number": self.roll_number,
            "Name": self.name,
            "Email": self.email,
            "Filename": filename,
            "Contact": self.contact,
            "Scaler CGPA": self.scaler_cgpa,
            "BITS CGPA": self.bits_cgpa,
        }


def _roll_from_email(email: str) -> str:
    match = ROLL_NUMBER_PATTERN.search(email or "")
    return match.group(0).lower() if match else ""


def _normalize_header_key(raw: str) -> str:
    """Normalize CSV header for alias lookup (Google Forms adds trailing colons)."""
    return str(raw).strip().lstrip("\ufeff").lower().replace("_", " ").rstrip(":").strip()


def load_form_csv(path: Path) -> list[FormApplication]:
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = _read_csv(path)

    # Extend aliases for form columns
    merged_aliases = {**COLUMN_ALIASES, **RESUME_URL_ALIASES}
    renamed: dict[str, str] = {}
    for col in df.columns:
        raw = str(col).strip().lstrip("\ufeff")
        key = _normalize_header_key(raw)
        renamed[col] = merged_aliases.get(key, raw)
    df = df.rename(columns=renamed)

    if "Resume" not in df.columns:
        for col in df.columns:
            sample = df[col].dropna().astype(str).head(8)
            if any("drive.google.com" in value for value in sample):
                df = df.rename(columns={col: "Resume"})
                break

    if "Resume" not in df.columns:
        raise ValueError(
            "CSV must include a Resume column with Google Drive links. "
            f"Found columns: {list(df.columns)}"
        )

    applications: list[FormApplication] = []
    for _, row in df.iterrows():
        resume_url = str(row.get("Resume", "")).strip()
        if not resume_url or resume_url.lower() == "nan":
            continue
        if not extract_google_drive_file_id(resume_url):
            continue

        email = str(row.get("Email", "")).strip()
        name = str(row.get("Name", "")).strip()
        if name.lower() == "nan":
            name = ""
        applications.append(
            FormApplication(
                name=name,
                email=email,
                contact=str(row.get("Contact", "")).strip(),
                scaler_cgpa=str(row.get("Scaler CGPA", row.get("Scaler CGF", ""))).strip(),
                bits_cgpa=str(row.get("BITS CGPA", "")).strip(),
                resume_url=resume_url,
                roll_number=_roll_from_email(email),
                timestamp=str(row.get("Timestamp", "")).strip(),
            )
        )

    if not applications:
        raise ValueError("No valid Google Drive resume links found in CSV.")
    return applications


async def download_form_resumes(
    applications: list[FormApplication],
    dest_dir: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[FormApplication]:
    dest_dir = Path(dest_dir)
    items = [(app.resume_url, app.name or app.email or "resume") for app in applications]
    downloaded = await download_google_drive_pdfs(
        items,
        dest_dir,
        progress_callback=progress_callback,
    )

    url_to_path = {url: path for url, path in downloaded}
    ready: list[FormApplication] = []
    for app in applications:
        path = url_to_path.get(app.resume_url)
        if path:
            app.local_pdf = path
            ready.append(app)
    return ready


def metadata_dict_from_applications(
    applications: list[FormApplication],
) -> dict[str, dict]:
    """Metadata keyed by roll / email — same shape as load_metadata()."""
    rows: dict[str, dict] = {}
    for app in applications:
        record = app.metadata_record("")
        roll = (app.roll_number or "").strip().lower()
        if roll and roll != "nan":
            rows[roll] = record
        email = (app.email or "").strip().lower()
        if email and email != "nan":
            rows[email] = record
    return rows


def save_metadata_for_applications(
    applications: list[FormApplication],
    path: Path,
) -> Path:
    records = [
        app.metadata_record(app.local_pdf.name)
        for app in applications
        if app.local_pdf
    ]
    df = pd.DataFrame(records)
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        df.to_excel(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
