"""Live smoke test: DuckDuckGo LinkedIn profile verification.

Usage:
    python scripts/test_linkedin_ddg.py
    python scripts/test_linkedin_ddg.py profiles.csv
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.links.linkedin_ddg import verify_linkedin_via_ddg

DEFAULT_SAMPLES = [
    ("Satya Nadella", "https://www.linkedin.com/in/satyanadella/"),
    ("Bill Gates", "https://www.linkedin.com/in/williamhgates/"),
]


def run_samples(samples: list[tuple[str, str]]) -> None:
    print(f"Testing {len(samples)} LinkedIn URLs via DuckDuckGo...\n")
    for i, (name, url) in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] {name}")
        print(f"  URL: {url}")
        result = verify_linkedin_via_ddg(url, name)
        print(f"  Status: {result.status}")
        print(f"  Details: {result.details}")
        if i < len(samples):
            time.sleep(2.5)


def run_csv(path: Path) -> None:
    out_path = path.parent / "validation_results.csv"
    with path.open(encoding="utf-8") as infile, out_path.open(
        "w", encoding="utf-8", newline=""
    ) as outfile:
        reader = csv.DictReader(infile)
        if not reader.fieldnames or "name" not in reader.fieldnames or "url" not in reader.fieldnames:
            raise SystemExit("CSV must have columns: name, url")

        writer = csv.DictWriter(
            outfile,
            fieldnames=["name", "url", "status", "extracted_details", "confidence_score"],
        )
        writer.writeheader()

        for i, row in enumerate(reader, 1):
            name = row["name"]
            url = row["url"]
            print(f"[{i}] {name}")
            result = verify_linkedin_via_ddg(url, name)
            writer.writerow(
                {
                    "name": name,
                    "url": url,
                    "status": result.status,
                    "extracted_details": result.details,
                    "confidence_score": "",
                }
            )
            time.sleep(2.5)

    print(f"\nDone. Results written to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_csv(Path(sys.argv[1]))
    else:
        run_samples(DEFAULT_SAMPLES)
