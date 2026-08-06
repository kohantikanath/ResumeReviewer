"""Tests for Excel report export."""

import json
from pathlib import Path

import pandas as pd

from app.extract.pdf_loader import extract_pdf
from app.report.exporter import _build_frames
from app.rules.base import EvaluationResult, RuleResult, Severity, Verdict
from app.types import VerificationOutcome
from app.report.exporter import export_report_xlsx

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_link_log_only_failed_urls():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Good 1.pdf"
    outcome = VerificationOutcome(
        path=FIXTURES / "Good 1.pdf",
        doc=doc,
        evaluation=EvaluationResult(
            verdict=Verdict.REVIEW,
            results=[
                RuleResult(
                    rule_id="R502",
                    severity=Severity.HARD,
                    passed=False,
                    reason="Broken hyperlink",
                    evidence="URL https://example.com/broken returned 404 at Line 8 | Projects, anchor text GitHub",
                ),
                RuleResult(
                    rule_id="R503",
                    severity=Severity.SOFT,
                    passed=False,
                    reason="Unverifiable hyperlink",
                    evidence="URL https://linkedin.com/in/foo returned 403 at Line 1 | Header, anchor text LinkedIn",
                ),
            ],
            hard_fail_count=1,
            soft_flag_count=1,
        ),
        link_statuses={
            "https://example.com/ok": (200, "ok"),
            "https://example.com/broken": (404, "ok"),
            "https://linkedin.com/in/foo": (403, "ok"),
        },
    )
    summary, details, links = _build_frames([outcome])
    urls = links["URL"].tolist()
    assert "https://example.com/ok" not in urls
    assert "https://example.com/broken" in urls
    assert "https://linkedin.com/in/foo" in urls
    assert links.loc[links["URL"] == "https://example.com/broken"]["Classification"].iloc[0] == "hard_fail"
    assert links.loc[links["URL"] == "https://linkedin.com/in/foo"]["Classification"].iloc[0] == "soft"
    assert "Line" in links.columns
    assert "Failed Rules (JSON)" in summary.columns
    failed = json.loads(summary["Failed Rules (JSON)"].iloc[0])
    assert len(failed) == 2
    assert all("rule_id" in x and "rule" in x and "reason" in x for x in failed)
    assert details["Reason"].str.contains("example.com/broken").any()


def test_export_report_xlsx_creates_three_sheets(tmp_path):
    from app.verify import verify_batch

    pdfs = sorted(FIXTURES.glob("Good *.pdf"))[:2]
    outcomes = verify_batch(pdfs, FIXTURES / "metadata.xlsx", check_links=False)
    out = export_report_xlsx(outcomes, tmp_path / "results.xlsx")

    assert out.exists()
    xl = pd.ExcelFile(out)
    assert xl.sheet_names == ["Summary", "Details", "Broken links"]

    summary = pd.read_excel(out, sheet_name="Summary")
    assert len(summary) == 2
    assert "Verdict" in summary.columns
