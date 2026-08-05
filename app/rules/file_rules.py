"""R1xx file and identity rules."""

import re
from pathlib import Path

from app.config import (
    FILENAME_PATTERN,
    MAX_FILE_BYTES,
    MIN_EXTRACTABLE_CHARS,
    NAME_FUZZY_THRESHOLD,
)
from app.models import DocumentModel
from app.rules.base import RuleResult, Severity

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


def check_file_rules(doc: DocumentModel, metadata_row: dict | None) -> list[RuleResult]:
    results: list[RuleResult] = []

    # R101
    extractable = len(doc.full_text.strip()) >= MIN_EXTRACTABLE_CHARS
    results.append(
        RuleResult(
            rule_id="R101",
            severity=Severity.HARD,
            passed=extractable,
            reason="PDF has insufficient extractable text (possibly scanned/image-based)",
            evidence=f"chars={len(doc.full_text.strip())}",
        )
    )

    # R102
    results.append(
        RuleResult(
            rule_id="R102",
            severity=Severity.HARD,
            passed=doc.file_size < MAX_FILE_BYTES,
            reason="File size exceeds 10MB limit",
            evidence=f"bytes={doc.file_size}",
        )
    )

    # R103 — skip for calibration filenames (Good N.pdf / Bad N.pdf)
    calib = re.match(r"^(Good|Bad)\s+\d+\.pdf$", doc.filename, re.I)
    roll_in_meta = False
    filename_ok = False
    evidence = doc.filename

    if not calib:
        m = FILENAME_PATTERN.match(doc.filename)
        filename_ok = m is not None
        roll = m.group(2).lower() if m else ""
        if metadata_row and roll:
            meta_roll = str(metadata_row.get("Roll Number", "")).lower()
            roll_in_meta = roll == meta_roll
        evidence = f"filename={doc.filename}, roll_in_meta={roll_in_meta}"

    results.append(
        RuleResult(
            rule_id="R103",
            severity=Severity.HARD,
            passed=calib is not None or (filename_ok and roll_in_meta),
            reason="Filename must match Name_RollNumber_SST.pdf and roll must exist in metadata",
            evidence=evidence,
        )
    )

    # R104
    name_match = True
    evidence = ""
    if metadata_row and doc.header_name and fuzz:
        meta_name = str(metadata_row.get("Name", ""))
        score = max(
            fuzz.token_sort_ratio(meta_name, doc.header_name),
            fuzz.partial_ratio(meta_name, doc.header_name),
        )
        name_match = score >= NAME_FUZZY_THRESHOLD
        evidence = f"pdf_name={doc.header_name}, meta_name={meta_name}, score={score}"

    results.append(
        RuleResult(
            rule_id="R104",
            severity=Severity.SOFT,
            passed=name_match if metadata_row else True,
            reason="Name in PDF header does not closely match metadata",
            evidence=evidence,
        )
    )

    return results
