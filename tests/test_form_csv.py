"""Tests for Google Drive link parsing and Forms CSV loading."""

from pathlib import Path

import pandas as pd

from app.drive import extract_google_drive_file_id
from app.form_csv import load_form_csv

SAMPLE_URL = "https://drive.google.com/open?id=18GMoKq5P5_8ybRMDWiH3Yst6vi11l-gU"


def test_extract_drive_file_id_open_link():
    assert extract_google_drive_file_id(SAMPLE_URL) == "18GMoKq5P5_8ybRMDWiH3Yst6vi11l-gU"


def test_extract_drive_file_id_file_link():
    url = "https://drive.google.com/file/d/abc123XYZ/view?usp=sharing"
    assert extract_google_drive_file_id(url) == "abc123XYZ"


def test_load_form_csv_google_forms_headers(tmp_path):
    """Google Forms exports use trailing colons: Name:, Contact Number:"""
    csv_path = tmp_path / "responses.csv"
    pd.DataFrame(
        {
            "Timestamp": ["2026-01-01"],
            "Email Address": ["swaim.24bcs10335@sst.scaler.com"],
            "Name:": ["Swaim Sahay"],
            "Contact Number:": ["9876543210"],
            "Scaler CGR": ["7.52"],
            "BITS CGPA": ["8.0"],
            "Resume": [SAMPLE_URL],
        }
    ).to_csv(csv_path, index=False)

    apps = load_form_csv(csv_path)
    assert len(apps) == 1
    assert apps[0].name == "Swaim Sahay"
    assert apps[0].roll_number == "24bcs10335"


def test_load_form_csv(tmp_path):
    csv_path = tmp_path / "responses.csv"
    pd.DataFrame(
        {
            "Timestamp": ["2026-01-01"],
            "Email Address": ["student.23bcs10151@sst.scaler.com"],
            "Name": ["Test Student"],
            "Contact Number": ["9876543210"],
            "Scaler CGPA": ["8.5"],
            "BITS CGPA": ["8.0"],
            "Resume": [SAMPLE_URL],
        }
    ).to_csv(csv_path, index=False)

    apps = load_form_csv(csv_path)
    assert len(apps) == 1
    assert apps[0].name == "Test Student"
    assert apps[0].roll_number == "23bcs10151"
    assert apps[0].resume_url == SAMPLE_URL
