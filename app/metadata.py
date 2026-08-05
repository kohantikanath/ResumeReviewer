"""Metadata sheet loading and PDF-derived auto-fill."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.extract.pdf_loader import derive_metadata, extract_pdf


METADATA_COLUMNS = ["Roll Number", "Name", "Email"]


def load_metadata(path: Path) -> dict[str, dict]:
    """Load metadata xlsx/csv keyed by roll number (lowercase)."""
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    df.columns = [str(c).strip() for c in df.columns]
    rows: dict[str, dict] = {}
    for _, row in df.iterrows():
        record = {col: str(row.get(col, "")).strip() for col in METADATA_COLUMNS if col in df.columns}
        roll = str(record.get("Roll Number", "")).strip().lower()
        if roll and roll != "nan":
            rows[roll] = record
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
        df.to_csv(path, index=False)


def match_metadata_row(
    doc_roll: str,
    metadata: dict[str, dict],
    derived: dict[str, str],
) -> dict | None:
    roll = (doc_roll or derived.get("Roll Number", "")).lower()
    if roll and roll in metadata:
        return metadata[roll]
    return None
