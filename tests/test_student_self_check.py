"""Student self-check filename vs header (no metadata)."""

from pathlib import Path

from app.extract.pdf_loader import extract_pdf
from app.rules.file_rules import check_file_rules

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_student_self_check_filename_matches_header():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Pooja_Talele_23bcs10151_SST.pdf"
    results = check_file_rules(doc, None, student_self_check=True)
    r103 = next(r for r in results if r.rule_id == "R103")
    r104 = next(r for r in results if r.rule_id == "R104")
    assert r103.passed
    assert r104.passed


def test_student_self_check_rejects_wrong_roll_in_filename():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Pooja_10011_SST.pdf"
    results = check_file_rules(doc, None, student_self_check=True)
    r103 = next(r for r in results if r.rule_id == "R103")
    assert not r103.passed
    assert "10011" in r103.reason or "10011" in r103.evidence


def test_student_self_check_portal_id_in_bcs_roll():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Pooja_Talele_10151_SST.pdf"
    results = check_file_rules(doc, None, student_self_check=True)
    r103 = next(r for r in results if r.rule_id == "R103")
    assert r103.passed


def test_student_self_check_rejects_calibration_filename():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Good 1.pdf"
    results = check_file_rules(doc, None, student_self_check=True)
    r103 = next(r for r in results if r.rule_id == "R103")
    r104 = next(r for r in results if r.rule_id == "R104")
    assert not r103.passed
    assert r104.passed  # duplicate name check suppressed — covered by R103
