"""Resolve PDF batches from metadata sheets and ZIP bundles."""

from __future__ import annotations

import zipfile
from pathlib import Path

from app.metadata import (
    FILENAME_COLUMNS,
    load_metadata_dataframe,
    metadata_filename,
    read_metadata_table,
)


def _find_metadata_in_dir(directory: Path) -> Path | None:
    for name in ("metadata.csv", "metadata.xlsx", "metadata.xls"):
        candidate = directory / name
        if candidate.exists():
            return candidate
    for pattern in ("*.csv", "*.xlsx", "*.xls"):
        matches = [p for p in directory.glob(pattern) if p.name.lower() != "results.xlsx"]
        if matches:
            return matches[0]
    return None


def list_pdfs_in_dir(directory: Path) -> dict[str, Path]:
    """Map lowercase filename -> path for all PDFs under directory."""
    mapping: dict[str, Path] = {}
    for path in directory.rglob("*.pdf"):
        key = path.name.lower()
        if key not in mapping:
            mapping[key] = path
    return mapping


def resolve_pdfs_from_metadata(
    metadata_path: Path,
    pdf_dir: Path,
    require_all: bool = True,
) -> list[Path]:
    """Return PDF paths listed in metadata Filename column (order preserved)."""
    df = load_metadata_dataframe(metadata_path)
    pdf_map = list_pdfs_in_dir(pdf_dir)
    filenames = metadata_filename(df)
    if not filenames:
        raise ValueError(
            "Metadata sheet has no Filename / Resume File column. "
            "Add a column listing each PDF filename, or upload PDFs directly."
        )

    resolved: list[Path] = []
    missing: list[str] = []
    for name in filenames:
        key = name.lower()
        if key not in pdf_map:
            missing.append(name)
            continue
        resolved.append(pdf_map[key])

    if require_all and missing:
        raise ValueError(
            f"PDFs listed in metadata not found in upload: {', '.join(missing[:5])}"
            + (" …" if len(missing) > 5 else "")
        )
    if not resolved:
        raise ValueError("No PDFs matched metadata filenames.")
    return resolved


def extract_zip_bundle(zip_path: Path, work_dir: Path) -> tuple[Path | None, list[Path]]:
    """Extract ZIP; return metadata path and PDF paths (CSV-driven if possible)."""
    extract_root = work_dir / "bundle"
    extract_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_root)

    metadata_path = _find_metadata_in_dir(extract_root)
    pdf_map = list_pdfs_in_dir(extract_root)

    if not pdf_map:
        raise ValueError("ZIP contains no PDF files.")

    if metadata_path:
        try:
            pdf_paths = resolve_pdfs_from_metadata(metadata_path, extract_root, require_all=True)
            return metadata_path, pdf_paths
        except ValueError as exc:
            if "no Filename" in str(exc):
                return metadata_path, sorted(pdf_map.values(), key=lambda p: p.name.lower())
            raise

    return None, sorted(pdf_map.values(), key=lambda p: p.name.lower())
