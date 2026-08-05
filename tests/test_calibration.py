"""Golden tests against 8 calibration samples."""

import json
from pathlib import Path

import pytest

from app.extract.pdf_loader import extract_pdf
from app.metadata import load_metadata
from app.verify import verify_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "samples"
EXPECTED = Path(__file__).parent / "fixtures" / "expected_verdicts.json"


@pytest.fixture
def expected():
    with open(EXPECTED, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def metadata():
    meta_path = FIXTURES / "metadata.xlsx"
    if meta_path.exists():
        return load_metadata(meta_path)
    return {}


@pytest.mark.parametrize(
    "filename",
    [
        "Good 1.pdf",
        "Good 2.pdf",
        "Good 3.pdf",
        "Good 4.pdf",
        "Bad 1.pdf",
        "Bad 2.pdf",
        "Bad 3.pdf",
        "Bad 4.pdf",
    ],
)
def test_verdict_matches_calibration(filename, expected, metadata):
    path = FIXTURES / filename
    doc, evaluation, _ = verify_pdf(path, metadata, check_links=False)
    exp = expected[filename]
    assert evaluation.verdict.value == exp["verdict"], (
        f"{filename}: expected {exp['verdict']}, got {evaluation.verdict.value}. "
        f"Failed: {evaluation.failed_rules()}"
    )

    failed = set(evaluation.failed_rules())
    for rule_id in exp["rules"]:
        assert rule_id in failed, f"{filename}: expected rule {rule_id} to fail"


def test_extraction_page_counts():
    assert extract_pdf(FIXTURES / "Good 1.pdf").page_count == 1
    assert extract_pdf(FIXTURES / "Bad 1.pdf").page_count == 2


def test_extraction_sections_good1():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    keys = {s.key for s in doc.sections}
    assert "education" in keys
    assert "skills" in keys
    assert "projects" in keys
    assert doc.header_name == "Pooja Talele"


def test_derived_metadata_has_roll_for_good_samples():
    doc = extract_pdf(FIXTURES / "Good 1.pdf")
    assert doc.metadata_derived["Roll Number"] == "23bcs10151"
    assert "@sst.scaler.com" in doc.metadata_derived["Email"]
