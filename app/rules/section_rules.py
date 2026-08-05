"""R4xx section and field rules."""

import re
from difflib import SequenceMatcher

from app.config import CGR_PATTERN, CGPA_PATTERN
from app.models import DocumentModel
from app.rules.base import RuleResult, Severity

URL_IN_TEXT = re.compile(r"https?://[^\s|]+|www\.[^\s|]+|[a-z0-9.-]+\.(com|in|dev|io|org)[^\s|]*", re.I)


def _has_college_names(text: str) -> bool:
    lower = text.lower()
    has_sst = "scaler school of technology" in lower or "sst" in lower
    has_bits = "bits" in lower or "pilani" in lower
    return has_sst and has_bits


def _has_degree_keywords(text: str) -> bool:
    lower = text.lower()
    return any(
        kw in lower
        for kw in [
            "computer science",
            "b.sc",
            "bachelor",
            "undergraduate",
            "integrated",
            "b.s",
        ]
    )


def _has_cgr_and_cgpa(text: str) -> bool:
    return CGR_PATTERN.search(text) is not None and CGPA_PATTERN.search(text) is not None


def _entry_has_link(entry_text: str, entry_links: list[str]) -> bool:
    if entry_links:
        return True
    return URL_IN_TEXT.search(entry_text) is not None


def _text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def check_section_rules(doc: DocumentModel) -> list[RuleResult]:
    results: list[RuleResult] = []

    edu = doc.section_by_key("education")
    skills = doc.section_by_key("skills")
    projects = doc.section_by_key("projects")

    results.append(
        RuleResult(
            rule_id="R401",
            severity=Severity.HARD,
            passed=edu is not None,
            reason="Education section not found",
            evidence="",
        )
    )

    results.append(
        RuleResult(
            rule_id="R402",
            severity=Severity.HARD,
            passed=skills is not None,
            reason="Skills section not found",
            evidence="",
        )
    )

    edu_ok = False
    edu_evidence = ""
    if edu:
        text = edu.text
        edu_ok = (
            _has_college_names(text)
            and _has_degree_keywords(text)
            and _has_cgr_and_cgpa(text)
        )
        if not _has_cgr_and_cgpa(text):
            edu_evidence = "Missing CGR or CGPA values"
        elif not _has_college_names(text):
            edu_evidence = "Missing college names"

    results.append(
        RuleResult(
            rule_id="R403",
            severity=Severity.HARD,
            passed=edu_ok,
            reason="Education must include colleges, degree, and both CGR and CGPA",
            evidence=edu_evidence,
        )
    )

    exp_section = doc.section_by_key("experience")
    exp_ok = True
    exp_evidence = ""
    if exp_section and doc.experiences:
        for entry in doc.experiences:
            lower = entry.text.lower()
            has_org = len(entry.title_line) > 2
            has_role = "\n" in entry.text or len(entry.text.split()) > 4
            has_duration = bool(
                re.search(
                    r"\d{4}|present|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec",
                    lower,
                )
            )
            has_location = bool(
                re.search(r"india|remote|bengaluru|bangalore|pilani", lower)
            )
            has_bullet = entry.has_description_bullet
            if not (has_org and has_role and has_duration and has_location and has_bullet):
                exp_ok = False
                exp_evidence = entry.title_line[:80]
                break

    results.append(
        RuleResult(
            rule_id="R404",
            severity=Severity.HARD,
            passed=exp_ok,
            reason="Experience entry missing org, role, duration, location, or description",
            evidence=exp_evidence,
        )
    )

    results.append(
        RuleResult(
            rule_id="R405",
            severity=Severity.HARD,
            passed=projects is not None and len(doc.projects) > 0,
            reason="Projects section is mandatory",
            evidence=f"projects={len(doc.projects)}",
        )
    )

    proj_ok = True
    proj_evidence = ""
    if projects:
        for proj in doc.projects:
            has_name = len(proj.title_line) > 2
            has_link = _entry_has_link(proj.title_line, proj.links)
            has_desc = proj.has_description_bullet
            if not (has_name and has_link and has_desc):
                proj_ok = False
                proj_evidence = proj.title_line[:100]
                break

    results.append(
        RuleResult(
            rule_id="R406",
            severity=Severity.HARD,
            passed=proj_ok,
            reason="Project missing name, link, or description bullet",
            evidence=proj_evidence,
        )
    )

    dup_ok = True
    dup_evidence = ""
    if exp_section and doc.experiences and doc.projects:
        for exp in doc.experiences:
            exp_key = exp.title_line.lower()
            exp_tokens = {w for w in re.findall(r"[a-z0-9]{4,}", exp_key)}
            for proj in doc.projects:
                proj_key = proj.title_line.lower()
                if _text_similarity(exp_key, proj_key) > 0.45:
                    dup_ok = False
                    dup_evidence = f"exp={exp.title_line[:40]}, proj={proj.title_line[:40]}"
                elif any(token in proj_key for token in exp_tokens):
                    dup_ok = False
                    dup_evidence = f"exp={exp.title_line[:40]}, proj={proj.title_line[:40]}"
                elif len(exp.text) > 40 and len(proj.text) > 40 and _text_similarity(exp.text[:200], proj.text[:200]) > 0.65:
                    dup_ok = False
                    dup_evidence = "Overlapping experience/project content"

    results.append(
        RuleResult(
            rule_id="R407",
            severity=Severity.SOFT,
            passed=dup_ok,
            reason="Duplicate content between Experience and Projects",
            evidence=dup_evidence,
        )
    )

    return results
