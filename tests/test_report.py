"""Tests for Excel report export."""

from pathlib import Path

import pandas as pd

from app.extract.pdf_loader import extract_pdf
from app.report.exporter import _build_frames
from app.rules.base import EvaluationResult, Verdict
from app.types import VerificationOutcome
from app.report.exporter import export_report_xlsx
from app.verify import verify_batch

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_link_log_only_failed_urls():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Good 1.pdf"
    outcome = VerificationOutcome(
        path=FIXTURES / "Good 1.pdf",
        doc=doc,
        evaluation=EvaluationResult(verdict=Verdict.PASS),
        link_statuses={
            "https://example.com/ok": (200, "ok"),
            "https://example.com/broken": (404, "ok"),
            "https://linkedin.com/in/foo": (403, "ok"),
        },
    )
    _, _, links = _build_frames([outcome])
    urls = links["URL"].tolist()
    assert "https://example.com/ok" not in urls
    assert "https://example.com/broken" in urls
    assert "https://linkedin.com/in/foo" in urls
    assert links.loc[links["URL"] == "https://example.com/broken"]["Classification"].iloc[0] == "hard_fail"
    assert links.loc[links["URL"] == "https://linkedin.com/in/foo"]["Classification"].iloc[0] == "soft"


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
