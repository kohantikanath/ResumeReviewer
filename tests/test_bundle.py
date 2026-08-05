"""Tests for ZIP bundle and CSV-driven PDF resolution."""

import zipfile
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.api.main import app
from app.bundle import extract_zip_bundle, resolve_pdfs_from_metadata

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def _make_bundle(tmp_path: Path, rows: list[dict], pdf_names: list[str]) -> Path:
    csv_path = tmp_path / "metadata.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    zip_path = tmp_path / "batch.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(csv_path, arcname="metadata.csv")
        for name in pdf_names:
            zf.write(FIXTURES / name, arcname=name)
    return zip_path


def test_resolve_pdfs_from_metadata_csv(tmp_path):
    rows = pd.read_excel(FIXTURES / "metadata.xlsx").head(2)
    csv_path = tmp_path / "meta.csv"
    rows.to_csv(csv_path, index=False)

    for name in rows["Source File"]:
        (tmp_path / name).write_bytes((FIXTURES / name).read_bytes())

    paths = resolve_pdfs_from_metadata(csv_path, tmp_path)
    assert len(paths) == 2
    assert {p.name for p in paths} == set(rows["Source File"])


def test_extract_zip_bundle(tmp_path):
    meta = pd.read_excel(FIXTURES / "metadata.xlsx").head(2)
    zip_path = _make_bundle(
        tmp_path,
        meta.to_dict(orient="records"),
        list(meta["Source File"]),
    )
    work = tmp_path / "work"
    meta_path, pdf_paths = extract_zip_bundle(zip_path, work)
    assert meta_path is not None
    assert len(pdf_paths) == 2


def test_api_batch_zip_upload(tmp_path):
    meta = pd.read_excel(FIXTURES / "metadata.xlsx").head(1)
    zip_path = _make_bundle(
        tmp_path,
        meta.to_dict(orient="records"),
        [meta.iloc[0]["Source File"]],
    )

    client = TestClient(app)
    with zip_path.open("rb") as zf:
        res = client.post(
            "/api/batch?check_links=false",
            files={"bundle": ("batch.zip", zf, "application/zip")},
        )
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    status = client.get(f"/api/jobs/{job_id}")
    assert status.json()["status"] == "completed"
