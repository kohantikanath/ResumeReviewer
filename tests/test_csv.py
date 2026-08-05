"""Tests for CSV metadata and CSV report export."""

from pathlib import Path

import pandas as pd

from app.metadata import load_metadata
from app.report.exporter import export_report_csv_zip
from app.verify import verify_batch

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_load_metadata_csv_with_aliases(tmp_path):
    csv_path = tmp_path / "meta.csv"
    pd.DataFrame(
        {
            "roll_no": ["23bcs10151"],
            "Student Name": ["Pooja Talele"],
            "college_email": ["pooja.23bcs10151@sst.scaler.com"],
        }
    ).to_csv(csv_path, index=False, encoding="utf-8-sig")

    meta = load_metadata(csv_path)
    assert "23bcs10151" in meta
    assert meta["23bcs10151"]["Name"] == "Pooja Talele"


def test_export_csv_zip(tmp_path):
    pdfs = sorted(FIXTURES.glob("Good *.pdf"))[:1]
    outcomes = verify_batch(pdfs, FIXTURES / "metadata.xlsx", check_links=False)
    zip_path = export_report_csv_zip(outcomes, tmp_path / "results_csv.zip")
    assert zip_path.exists()
    assert zip_path.stat().st_size > 0
