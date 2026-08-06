"""Human-readable failure reasons for report JSON."""

from __future__ import annotations

import json
import re

from app.models import DocumentModel
from app.rules.base import RuleResult

RULE_TITLES: dict[str, str] = {
    "R101": "Valid text-extractable PDF",
    "R102": "File size under 10MB",
    "R103": "Filename matches convention and roll in metadata",
    "R104": "Name in PDF matches metadata",
    "R201": "Exactly one page",
    "R202": "No embedded images",
    "R203": "No emojis",
    "R301": "Student name present at top",
    "R302": "Phone number present",
    "R303": "College email displayed",
    "R304": "Displayed email matches mailto target",
    "R305": "LinkedIn link in header",
    "R306": "GitHub link in header",
    "R307": "LinkedIn slug matches student name",
    "R401": "Education section exists",
    "R402": "Skills section exists",
    "R403": "Education has college, degree, CGR/CGPA",
    "R404": "Experience entries complete",
    "R405": "Projects section exists",
    "R406": "Project has name, link, and description",
    "R407": "No duplicate Experience/Projects content",
    "R501": "No malformed or placeholder URLs",
    "R502": "Broken hyperlink",
    "R503": "Unverifiable hyperlink",
    "R504": "GitHub username consistency",
    "R505": "No tracking parameters in URLs",
}


def rule_title(rule_id: str, fallback: str = "") -> str:
    return RULE_TITLES.get(rule_id, fallback or rule_id)


def build_failure_reason(result: RuleResult, doc: DocumentModel | None = None) -> str:
    """Turn rule evidence into a mandatory human justification."""
    rid = result.rule_id
    ev = (result.evidence or "").strip()

    if rid == "R101":
        chars = ev.replace("chars=", "") if ev.startswith("chars=") else ev
        return (
            f"Only {chars} extractable characters found; minimum 200 required "
            "(PDF may be scanned or image-based)"
        )

    if rid == "R102":
        mb = ev.replace("bytes=", "")
        try:
            size_mb = int(mb) / (1024 * 1024)
            return f"File size is {size_mb:.2f} MB which exceeds the 10 MB limit"
        except ValueError:
            return f"File size exceeds 10 MB limit ({ev})"

    if rid == "R103":
        return (
            f"Filename '{doc.filename if doc else ev}' does not match required "
            "pattern {Name}_{roll}_SST and roll was not found in metadata"
        )

    if rid == "R104":
        return ev or result.reason

    if rid == "R201":
        return f"Resume has {ev.replace('pages=', '')} page(s); exactly 1 page is required"

    if rid == "R202":
        return f"Resume contains {ev.replace('images=', '')} embedded image(s), which are not allowed"

    if rid == "R203":
        return f"Resume contains emoji '{ev}' which is not allowed"

    if rid == "R301":
        return "Student name was not detected at the top of the resume"

    if rid == "R302":
        return "No phone number found in the resume header"

    if rid == "R303":
        emails = re.findall(r"[\w.+-]+@[\w.-]+", ev)
        if emails:
            return (
                f"Found email '{emails[0]}' in header but it does not use the required "
                "@sst.scaler.com domain"
            )
        return "No @sst.scaler.com college email found in the resume header"

    if rid == "R304":
        if ev.startswith("displayed="):
            parts = ev.split(", mailto=")
            displayed = parts[0].replace("displayed=", "")
            mailto = parts[1] if len(parts) > 1 else ""
            if mailto:
                return (
                    f"Displayed email '{displayed}' does not match mailto target '{mailto}'"
                )
            return f"Displayed email '{displayed}' has no matching mailto link"
        if ev == "No mailto link for displayed email":
            return f"Email '{ev}' — displayed college email has no clickable mailto link"
        return ev or "Displayed email and mailto link do not match"

    if rid == "R305":
        return "LinkedIn profile link is missing from the resume header"

    if rid == "R306":
        return "GitHub profile link is missing from the resume header"

    if rid in {"R502", "R503"}:
        return ev or result.reason

    if rid == "R403":
        if "CGR" in ev or "CGPA" in ev:
            return "Education section is missing CGR or CGPA values (both are required)"
        if "college" in ev.lower():
            return "Education section does not list both SST and BITS college names"
        return "Education section is missing college names, degree, or CGR/CGPA"

    if rid == "R404":
        return f"Experience entry '{ev}' is missing organization, role, duration, location, or description bullet"

    if rid == "R406":
        return f"Project '{ev}' is missing a name, hyperlink, or description bullet"

    if rid == "R405":
        return "Projects section is missing or has no project entries"

    if rid in {"R401", "R402"}:
        return result.reason

    if ev:
        return ev
    return result.reason


def failures_to_json_records(
    results: list[RuleResult],
    doc: DocumentModel | None = None,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for result in results:
        if result.passed:
            continue
        records.append(
            {
                "rule_id": result.rule_id,
                "rule": rule_title(result.rule_id, result.reason),
                "reason": build_failure_reason(result, doc),
            }
        )
    return records


def failures_to_json_string(results: list[RuleResult], doc: DocumentModel | None = None) -> str:
    return json.dumps(failures_to_json_records(results, doc), ensure_ascii=False)
