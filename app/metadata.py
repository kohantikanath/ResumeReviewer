"""Metadata sheet loading and PDF-derived auto-fill."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.extract.pdf_loader import derive_metadata, extract_pdf


METADATA_COLUMNS = ["Roll Number", "Name", "Email"]
FILENAME_COLUMNS = ["Filename", "Resume File", "Source File", "PDF", "Resume", "File"]

COLUMN_ALIASES: dict[str, str] = {
    "roll number": "Roll Number",
    "roll no": "Roll Number",
    "roll no.": "Roll Number",
    "roll_no": "Roll Number",
    "rollnumber": "Roll Number",
    "roll": "Roll Number",
    "name": "Name",
    "student name": "Name",
    "student_name": "Name",
    "email": "Email",
    "email address": "Email",
    "college email": "Email",
    "college_email": "Email",
    "sst email": "Email",
    "filename": "Filename",
    "resume file": "Resume File",
    "resume filename": "Filename",
    "pdf": "PDF",
    "pdf file": "Filename",
    "source file": "Source File",
    "file": "Filename",
    "resume": "Resume",
    "resume path": "Resume Path",
    "file path": "Resume Path",
    "pdf path": "Resume Path",
    "contact": "Contact",
    "contact number": "Contact",
    "scaler cgpa": "Scaler CGPA",
    "scaler cgf": "Scaler CGPA",
    "scaler cgr": "Scaler CGPA",
    "bits cgpa": "BITS CGPA",
    "timestamp": "Timestamp",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[str, str] = {}
    for col in df.columns:
        raw = str(col).strip().lstrip("\ufeff")
        key = raw.lower().replace("_", " ")
        renamed[col] = COLUMN_ALIASES.get(key, raw)
    return df.rename(columns=renamed)


def _read_csv(path: Path) -> pd.DataFrame:
    attempts = [
        {"encoding": "utf-8-sig"},
        {"encoding": "utf-8"},
        {"encoding": "latin-1"},
        {"encoding": "utf-8-sig", "sep": ";"},
        {"encoding": "utf-8", "sep": ";"},
    ]
    last_error: Exception | None = None
    for opts in attempts:
        try:
            return pd.read_csv(path, **opts)
        except Exception as exc:
            last_error = exc
    if last_error:
        raise ValueError(f"Could not read CSV metadata: {last_error}")
    raise ValueError("Could not read CSV metadata")


def read_metadata_table(path: Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    elif suffix in {".csv", ".txt"}:
        df = _read_csv(path)
    else:
        raise ValueError(
            f"Unsupported metadata format '{suffix}'. Use .xlsx, .xls, or .csv"
        )
    return _normalize_columns(df)


def load_metadata_dataframe(path: Path) -> pd.DataFrame:
    return read_metadata_table(path)


def metadata_filename(df: pd.DataFrame) -> list[str]:
    """Ordered PDF filenames from metadata sheet."""
    for col in FILENAME_COLUMNS:
        if col in df.columns:
            names = [
                str(v).strip()
                for v in df[col].tolist()
                if str(v).strip() and str(v).strip().lower() != "nan"
            ]
            if names:
                return names
    return []


def load_metadata(path: Path) -> dict[str, dict]:
    """Load metadata xlsx/csv keyed by roll number (lowercase)."""
    df = read_metadata_table(path)
    rows: dict[str, dict] = {}
    for _, row in df.iterrows():
        record = {
            col: str(row.get(col, "")).strip()
            for col in METADATA_COLUMNS + FILENAME_COLUMNS
            if col in df.columns
        }
        roll = str(record.get("Roll Number", "")).strip().lower()
        if roll and roll != "nan":
            rows[roll] = record
        email = str(record.get("Email", "")).strip().lower()
        if email and email != "nan":
            rows[email] = record
    return rows


def build_metadata_from_pdfs(pdf_paths: list[Path]) -> pd.DataFrame:
    """Derive metadata rows from PDF content (name, roll from email, college email)."""
    records = []
    for path in pdf_paths:
        doc = extract_pdf(path)
        derived = derive_metadata(doc)
        records.append(
            {
                "Roll Number": derived.get("Roll Number", ""),
                "Name": derived.get("Name", ""),
                "Email": derived.get("Email", ""),
                "Source File": path.name,
            }
        )
    return pd.DataFrame(records)


def save_metadata(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        df.to_excel(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")


def match_metadata_row(
    doc_roll: str,
    metadata: dict[str, dict],
    derived: dict[str, str],
) -> dict | None:
    roll = (doc_roll or derived.get("Roll Number", "")).lower()
    if roll and roll in metadata:
        return metadata[roll]
    email = (derived.get("Email", "") or "").lower()
    if email and email in metadata:
        return metadata[email]
    return None
