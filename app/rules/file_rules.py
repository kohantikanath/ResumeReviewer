"""R1xx file and identity rules."""

import re
from pathlib import Path

from app.config import (
    FILENAME_PATTERN_BCS_ROLL,
    FILENAME_PATTERN_BCS_SST,
    FILENAME_PATTERN_NUMERIC_SST,
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


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _names_match(meta_name: str, pdf_name: str) -> bool:
    """Case-insensitive name match; ignores capitalization differences."""
    a = _normalize_name(meta_name)
    b = _normalize_name(pdf_name)
    if not a or not b:
        return True
    if a == b:
        return True
    if a in b or b in a:
        return True
    if fuzz:
        return max(
            fuzz.token_sort_ratio(a, b),
            fuzz.token_set_ratio(a, b),
            fuzz.partial_ratio(a, b),
        ) >= NAME_FUZZY_THRESHOLD
    return a == b


def _filename_stem(filename: str) -> str:
    """Strip .pdf and optional Superset suffix: '..._SST - Display Name'."""
    stem = Path(filename).stem.strip()
    if " - " in stem:
        return stem.split(" - ", 1)[0].strip()
    return stem


def _compact_name_matches(compact_part: str, full_name: str) -> bool:
    """Match SwaimSahay to Swaim Sahay (portal compact name prefix)."""
    if not compact_part or not full_name:
        return False
    alnum_compact = re.sub(r"[^a-z0-9]", "", compact_part.lower())
    alnum_full = re.sub(r"[^a-z0-9]", "", full_name.lower())
    if alnum_compact and alnum_compact == alnum_full:
        return True
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", compact_part).replace("_", " ")
    return _names_match(full_name, spaced)


def _filename_matches_student_name(
    filename: str, meta_name: str, header_name: str
) -> bool:
    stem = _filename_stem(filename)
    for candidate in (meta_name, header_name):
        if not candidate:
            continue
        if _names_match(candidate, stem.replace("_", " ")):
            return True
        for pattern in (FILENAME_PATTERN_BCS_SST, FILENAME_PATTERN_NUMERIC_SST):
            m = pattern.match(stem)
            if m and _compact_name_matches(m.group(1), candidate):
                return True
    return False


def _parse_filename_roll(filename: str) -> tuple[bool, str, str]:
    """Return (matched, name_part, roll/id) from known filename patterns."""
    stem = _filename_stem(filename)
    for pattern in (
        FILENAME_PATTERN_BCS_SST,
        FILENAME_PATTERN_NUMERIC_SST,
        FILENAME_PATTERN_BCS_ROLL,
    ):
        m = pattern.match(stem)
        if m:
            return True, m.group(1), m.group(2).lower()
    return False, "", ""


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

    # R103 — {Name}_{roll|id}_SST or portal compact formats; optional " - Display Name"
    calib = re.match(r"^(Good|Bad)\s+\d+\.pdf$", doc.filename, re.I)
    roll_in_meta = False
    filename_ok = False
    superset_name_ok = False
    roll = ""
    evidence = doc.filename

    if not calib:
        matched, _, roll = _parse_filename_roll(doc.filename)
        filename_ok = matched
        if metadata_row and roll:
            meta_roll = str(metadata_row.get("Roll Number", "")).strip().lower()
            roll_in_meta = roll == meta_roll
        if metadata_row:
            meta_name = str(metadata_row.get("Name", ""))
            superset_name_ok = _filename_matches_student_name(
                doc.filename, meta_name, doc.header_name
            )
        evidence = (
            f"stem={_filename_stem(doc.filename)}, roll={roll}, "
            f"roll_in_meta={roll_in_meta}, name_match={superset_name_ok}"
        )

    r103_pass = calib is not None or (filename_ok and roll_in_meta) or superset_name_ok

    results.append(
        RuleResult(
            rule_id="R103",
            severity=Severity.HARD,
            passed=r103_pass,
            reason="Filename must match {Name}_{id}_SST (bcs roll or numeric portal id)",
            evidence=evidence,
        )
    )

    # R104 — case-insensitive; capitalization differences ignored
    name_match = True
    evidence = ""
    if metadata_row and doc.header_name:
        meta_name = str(metadata_row.get("Name", ""))
        name_match = _names_match(meta_name, doc.header_name)
        evidence = (
            f"pdf_name={doc.header_name}, meta_name={meta_name}, "
            f"match={name_match}"
        )

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
