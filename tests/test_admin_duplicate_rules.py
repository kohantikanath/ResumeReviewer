"""Admin batch: avoid duplicate R103 + R104 failures."""

from pathlib import Path

from app.extract.pdf_loader import extract_pdf
from app.rules.file_rules import check_file_rules

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_admin_r104_suppressed_when_r103_fails():
    """Wrong filename/roll for metadata row — R103 only, not duplicate R104."""
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "WrongPerson_23bcs99999_SST.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "23bcs10151", "Name": "Pooja Talele", "Email": ""},
        student_self_check=False,
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    r104 = next(r for r in results if r.rule_id == "R104")
    assert not r103.passed
    assert r104.passed


def test_admin_r104_runs_when_r103_passes_calib():
    """Calibration filename skips R103 — R104 still checks metadata vs PDF header."""
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Bad 3.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "23bcs10151", "Name": "Bad 3", "Email": ""},
        student_self_check=False,
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    r104 = next(r for r in results if r.rule_id == "R104")
    assert r103.passed
    assert not r104.passed


def test_admin_r104_runs_when_r103_passes():
    """When R103 passes, R104 still checks metadata name vs PDF header."""
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Pooja_Talele_23bcs10151_SST.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "23bcs10151", "Name": "Navneet Kumar", "Email": ""},
        student_self_check=False,
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    r104 = next(r for r in results if r.rule_id == "R104")
    assert r103.passed
    assert not r104.passed
