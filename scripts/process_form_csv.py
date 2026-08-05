"""
Download resumes from Google Drive links in a Forms CSV and run verification.

Example CSV columns (Google Forms export):
  Timestamp, Email Address, Name, Contact Number, Scaler CGPA, BITS CGPA, Resume

Usage:
  python scripts/process_form_csv.py "responses.csv" --output-dir ./output
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.form_pipeline import process_form_csv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download resumes from Google Drive (Forms CSV) and verify"
    )
    parser.add_argument("csv_path", type=Path, help="Path to Google Forms CSV export")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for downloaded PDFs and reports",
    )
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="Run live HTTP link checks (slower)",
    )
    args = parser.parse_args()

    outcomes, xlsx, csv_zip = process_form_csv(
        args.csv_path,
        args.output_dir,
        check_links=args.check_links,
    )

    print(f"Processed {len(outcomes)} resumes")
    print(f"Excel report: {xlsx}")
    print(f"CSV bundle:   {csv_zip}")
    for o in outcomes:
        print(f"  {o.filename}: {o.evaluation.verdict.value}")


if __name__ == "__main__":
    main()
