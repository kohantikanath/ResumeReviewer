"""R1xx file and identity rules."""

import re
from pathlib import Path

from app.config import (
    FILENAME_PATTERN_BCS_ROLL,
    FILENAME_PATTERN_BCS_SST,
    FILENAME_PATTERN_NUMERIC_SST,
    MAX_FILE_BYTES,
    MIN_EXTRACTABLE_CHARS,
)
from app.models import DocumentModel
from app.rules.base import RuleResult, Severity
from app.rules.name_match import NameMatchOutcome, evaluate_name_match

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _names_match(meta_name: str, pdf_name: str) -> bool:
    """Legacy helper — use evaluate_name_match for severity-aware checks."""
    return evaluate_name_match(meta_name, pdf_name).outcome == NameMatchOutcome.PASS


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


def _roll_in_download_filename(filename: str, meta_roll: str) -> bool:
    """Drive downloads may rename files; roll embedded in stem still counts."""
    if not meta_roll:
        return False
    stem = re.sub(r"[^a-z0-9]", "", _filename_stem(filename).lower())
    roll = re.sub(r"[^a-z0-9]", "", meta_roll.lower())
    return roll and roll in stem


def filename_display_name(filename: str) -> str:
    matched, name_part, _ = _parse_filename_roll(filename)
    if matched and name_part:
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name_part)
        return spaced.replace("_", " ").strip()
    return _filename_stem(filename).replace("_", " ").strip()


def evaluate_filename_header_match(filename: str, header_name: str) -> NameMatchResult:
    return evaluate_name_match(filename_display_name(filename), header_name)


def _normalize_roll_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _filename_roll_matches_pdf(
    filename: str, pdf_roll: str, college_email: str = ""
) -> tuple[bool, str]:
    """Filename roll/id must agree with roll or email embedded in the PDF."""
    matched, _, file_roll = _parse_filename_roll(filename)
    if not matched or not file_roll:
        return False, "could not parse roll/id from filename"

    file_roll_norm = _normalize_roll_token(file_roll)
    pdf_roll_norm = _normalize_roll_token(pdf_roll)
    if not pdf_roll_norm:
        return False, "no roll number found inside PDF"

    stem = _filename_stem(filename)
    if FILENAME_PATTERN_BCS_SST.match(stem) or FILENAME_PATTERN_BCS_ROLL.match(stem):
        if file_roll_norm == pdf_roll_norm:
            return True, ""
        return (
            False,
            f"filename roll '{file_roll}' does not match PDF roll '{pdf_roll}'",
        )

    # Numeric Superset portal id — must appear inside the bcs roll or college email
    if file_roll_norm and file_roll_norm in pdf_roll_norm:
        return True, ""
    if college_email:
        email_local = _normalize_roll_token(college_email.split("@")[0])
        if file_roll_norm and file_roll_norm in email_local:
            return True, ""

    return (
        False,
        f"filename id '{file_roll}' does not match PDF roll '{pdf_roll}'",
    )


def check_file_rules(
    doc: DocumentModel,
    metadata_row: dict | None,
    student_self_check: bool = False,
) -> list[RuleResult]:
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
    roll_in_download_name = False
    filename_ok = False
    superset_name_ok = False
    roll = ""
    evidence = doc.filename
    meta_roll = ""

    if not calib or student_self_check:
        matched, _, roll = _parse_filename_roll(doc.filename)
        filename_ok = matched
        if metadata_row:
            meta_roll = str(metadata_row.get("Roll Number", "")).strip().lower()
            if roll and meta_roll:
                roll_in_meta = roll == meta_roll
            roll_in_download_name = _roll_in_download_filename(doc.filename, meta_roll)
            meta_name = str(metadata_row.get("Name", ""))
            if meta_name.lower() == "nan":
                meta_name = ""
            superset_name_ok = _filename_matches_student_name(
                doc.filename, meta_name, doc.header_name
            )
        if not student_self_check:
            evidence = (
                f"stem={_filename_stem(doc.filename)}, roll={roll}, meta_roll={meta_roll}, "
                f"roll_in_meta={roll_in_meta}, roll_in_download={roll_in_download_name}, "
                f"name_match={superset_name_ok}"
            )

    if student_self_check and not metadata_row:
        header_name_ok = _filename_matches_student_name(
            doc.filename, doc.header_name, doc.header_name
        )
        pdf_roll = str(doc.metadata_derived.get("Roll Number", ""))
        pdf_email = str(doc.metadata_derived.get("Email", ""))
        roll_matches_pdf, roll_reason = _filename_roll_matches_pdf(
            doc.filename, pdf_roll, pdf_email
        )
        r103_pass = filename_ok and header_name_ok and roll_matches_pdf
        evidence = (
            f"student_self_check stem={_filename_stem(doc.filename)}, "
            f"pattern_ok={filename_ok}, header_name_ok={header_name_ok}, "
            f"roll_in_pdf={pdf_roll}, roll_match={roll_matches_pdf}, {roll_reason}"
        )
        if not filename_ok:
            r103_reason = (
                f"Filename '{doc.filename}' does not follow {{Name}}_{{id}}_SST "
                "(bcs roll or numeric portal id)"
            )
        elif not header_name_ok:
            r103_reason = (
                f"Name in filename does not match name at top of PDF "
                f"('{filename_display_name(doc.filename)}' vs '{doc.header_name}')"
            )
        elif not roll_matches_pdf and roll_reason:
            r103_reason = f"Filename roll/id does not match PDF: {roll_reason}"
        else:
            r103_reason = "Filename must match {Name}_{id}_SST (bcs roll or numeric portal id)"
    elif calib is not None:
        r103_pass = True
        r103_reason = "Filename must match {Name}_{id}_SST (bcs roll or numeric portal id)"
    else:
        r103_pass = (
            (filename_ok and roll_in_meta)
            or superset_name_ok
            or roll_in_download_name
        )
        r103_reason = "Filename must match {Name}_{id}_SST (bcs roll or numeric portal id)"

    results.append(
        RuleResult(
            rule_id="R103",
            severity=Severity.HARD,
            passed=r103_pass,
            reason=r103_reason,
            evidence=evidence,
        )
    )

    # R104 — partial name match; surname-only = SOFT, truncation = HARD
    name_passed = True
    name_severity = Severity.SOFT
    name_reason = "Name in PDF header does not match metadata"
    name_evidence = ""
    if student_self_check and not metadata_row and doc.header_name:
        # R103 already checks filename vs PDF header; skip duplicate R104 when that failed
        if not r103_pass and (not filename_ok or not header_name_ok):
            name_passed = True
            name_evidence = "Already reported under R103 (filename vs PDF header)"
        else:
            match = evaluate_filename_header_match(doc.filename, doc.header_name)
            name_passed = match.outcome == NameMatchOutcome.PASS
            name_reason = "Filename name does not match name in PDF header"
            name_evidence = match.reason
            if match.outcome == NameMatchOutcome.HARD_FAIL:
                name_severity = Severity.HARD
            elif match.outcome == NameMatchOutcome.SOFT_FAIL:
                name_severity = Severity.SOFT
    elif metadata_row and doc.header_name:
        meta_name = str(metadata_row.get("Name", ""))
        if meta_name.lower() == "nan":
            meta_name = ""
        if meta_name:
            if not r103_pass:
                # Filename/roll vs metadata already failed in R103 — avoid duplicate R104
                name_passed = True
                name_evidence = "Filename/name vs metadata covered by R103"
            else:
                match = evaluate_name_match(meta_name, doc.header_name)
                name_passed = match.outcome == NameMatchOutcome.PASS
                name_evidence = match.reason
                if match.outcome == NameMatchOutcome.HARD_FAIL:
                    name_severity = Severity.HARD
                elif match.outcome == NameMatchOutcome.SOFT_FAIL:
                    name_severity = Severity.SOFT

    results.append(
        RuleResult(
            rule_id="R104",
            severity=name_severity,
            passed=name_passed if metadata_row or student_self_check else True,
            reason=name_reason,
            evidence=name_evidence,
        )
    )

    return results
