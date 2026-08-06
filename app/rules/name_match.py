"""R104 name matching: partial names, concatenation, truncation rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class NameMatchOutcome(str, Enum):
    PASS = "pass"
    SOFT_FAIL = "soft_fail"
    HARD_FAIL = "hard_fail"


@dataclass
class NameMatchResult:
    outcome: NameMatchOutcome
    reason: str = ""


def _name_parts(name: str) -> list[str]:
    parts: list[str] = []
    for part in (name or "").split():
        cleaned = re.sub(r"[^a-z0-9]", "", part.lower())
        if cleaned:
            parts.append(cleaned)
    return parts


def evaluate_name_match(meta_name: str, pdf_name: str) -> NameMatchResult:
    """
    Match metadata name to PDF header name.

    PASS: full name, first name only, first+middle prefix, concatenated (Kohantikanath).
    SOFT_FAIL: surname only (Nath).
    HARD_FAIL: truncated garbage (kohan), partial with junk (kohantikaN).
    """
    meta_parts = _name_parts(meta_name)
    pdf_parts = _name_parts(pdf_name)

    if not meta_parts:
        return NameMatchResult(NameMatchOutcome.PASS, "")

    if not pdf_parts:
        return NameMatchResult(
            NameMatchOutcome.SOFT_FAIL,
            f"No name found in resume header; metadata name is '{meta_name.strip()}'",
        )

    pdf_compact = "".join(pdf_parts)
    meta_compact = "".join(meta_parts)

    if pdf_parts == meta_parts or pdf_compact == meta_compact:
        return NameMatchResult(NameMatchOutcome.PASS, "")

    if len(pdf_parts) <= len(meta_parts):
        if all(pdf_parts[i] == meta_parts[i] for i in range(len(pdf_parts))):
            return NameMatchResult(NameMatchOutcome.PASS, "")

    if len(meta_parts) <= len(pdf_parts):
        if all(meta_parts[i] == pdf_parts[i] for i in range(len(meta_parts))):
            return NameMatchResult(NameMatchOutcome.PASS, "")

    for k in range(1, len(meta_parts) + 1):
        if pdf_compact == "".join(meta_parts[:k]):
            return NameMatchResult(NameMatchOutcome.PASS, "")

    if len(meta_parts) > 1 and pdf_parts == [meta_parts[-1]]:
        return NameMatchResult(
            NameMatchOutcome.SOFT_FAIL,
            f"Resume header shows only surname '{pdf_name.strip()}' but metadata name is '{meta_name.strip()}'",
        )

    if len(meta_parts) > 1 and len(pdf_parts) == 1 and pdf_compact == meta_parts[-1]:
        return NameMatchResult(
            NameMatchOutcome.SOFT_FAIL,
            f"Resume header shows only surname '{pdf_name.strip()}' but metadata name is '{meta_name.strip()}'",
        )

    if len(pdf_parts) == 1 and len(meta_parts) > 1:
        first_meta = meta_parts[0]
        pdf_token = pdf_parts[0]
        if pdf_token != first_meta:
            if first_meta.startswith(pdf_token) and len(pdf_token) < len(first_meta):
                return NameMatchResult(
                    NameMatchOutcome.HARD_FAIL,
                    f"'{pdf_name.strip()}' is an incomplete truncation of first name "
                    f"'{meta_parts[0]}' (expected '{meta_name.strip()}')",
                )
            if pdf_token.startswith(first_meta) and len(pdf_token) > len(first_meta):
                return NameMatchResult(
                    NameMatchOutcome.HARD_FAIL,
                    f"'{pdf_name.strip()}' is not a valid form of '{meta_name.strip()}' "
                    f"(extra characters after '{meta_parts[0]}')",
                )

    return NameMatchResult(
        NameMatchOutcome.HARD_FAIL,
        f"Resume name '{pdf_name.strip()}' does not match metadata name '{meta_name.strip()}'",
    )
