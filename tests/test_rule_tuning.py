"""Tests for relaxed R103/R104 and link location."""

from app.extract.link_locate import build_link_location_map
from app.extract.pdf_loader import extract_pdf
from app.rules.file_rules import _names_match, check_file_rules
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_r104_case_insensitive():
    assert _names_match("Pooja Talele", "POOJA TALELE")
    assert _names_match("kumar kartikay", "Kumar Kartikay")
    assert _names_match("Neel", "Neel Dholiya")


def test_r103_portal_numeric_filename():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "SwaimSahay_10335_SST - Swaim Sahay.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "10335", "Name": "Swaim Sahay", "Email": ""},
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    assert r103.passed


def test_r103_portal_numeric_without_display_suffix():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "SwaimSahay_10335_SST.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "10335", "Name": "Swaim Sahay", "Email": ""},
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    assert r103.passed


def test_r103_bcs_roll_still_works():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Pooja_Talele_23bcs10151_SST.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "23bcs10151", "Name": "Pooja Talele", "Email": ""},
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    assert r103.passed


def test_r103_drive_download_filename_with_roll_in_stem():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "swaim24bcs10335sstscalercom_1YoiulmS.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "24bcs10335", "Name": "Swaim Sahay", "Email": ""},
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    assert r103.passed


def test_r103_superset_name_only_filename():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    doc.filename = "Pooja_Talele.pdf"
    results = check_file_rules(
        doc,
        {"Roll Number": "23bcs10151", "Name": "Pooja Talele", "Email": ""},
    )
    r103 = next(r for r in results if r.rule_id == "R103")
    assert r103.passed


def test_link_location_map_good1():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    locs = build_link_location_map(doc)
    assert locs
    assert any("line" in v for v in locs.values())
