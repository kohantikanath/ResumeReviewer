"""Tests for Excel report export."""

from pathlib import Path

import pandas as pd

from app.report.exporter import export_report_xlsx
from app.verify import verify_batch

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_export_report_xlsx_creates_three_sheets(tmp_path):
    pdfs = sorted(FIXTURES.glob("Good *.pdf"))[:2]
    outcomes = verify_batch(pdfs, FIXTURES / "metadata.xlsx", check_links=False)
    out = export_report_xlsx(outcomes, tmp_path / "results.xlsx")

    assert out.exists()
    xl = pd.ExcelFile(out)
    assert xl.sheet_names == ["Summary", "Details", "Link log"]

    summary = pd.read_excel(out, sheet_name="Summary")
    assert len(summary) == 2
    assert "Verdict" in summary.columns
