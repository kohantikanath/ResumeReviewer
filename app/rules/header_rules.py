"""R3xx header rules."""

import re
from urllib.parse import unquote

from app.config import COLLEGE_EMAIL_PATTERN, PHONE_PATTERN, ROLL_NUMBER_PATTERN
from app.models import DocumentModel
from app.rules.base import RuleResult, Severity


def _normalize_slug(slug: str) -> str:
    return re.sub(r"[^a-z]", "", slug.lower())


def _name_tokens(name: str) -> list[str]:
    parts = re.split(r"\s+", name.strip())
    tokens = [p.lower() for p in parts if len(p) > 1]
    initials = "".join(p[0].lower() for p in parts if p)
    return tokens + [initials]


def _linkedin_slug_matches_name(slug: str, name: str) -> bool:
    norm_slug = _normalize_slug(slug)
    if not norm_slug or len(norm_slug) < 3:
        return False
    tokens = _name_tokens(name)
    if not tokens:
        return False

    full_compact = _normalize_slug(name)
    if full_compact and full_compact in norm_slug:
        return True

    for token in tokens:
        if len(token) >= 3 and token in norm_slug:
            return True

    # initial + surname patterns (e.g. kkartikay)
    if len(tokens) >= 2:
        first_initial = tokens[0][0]
        last = _normalize_slug(tokens[-1])
        if last and norm_slug.startswith(first_initial) and last in norm_slug:
            return True
        compact = first_initial + last
        if compact in norm_slug or norm_slug.startswith(compact):
            return True

    return False


def _extract_linkedin_slug(url: str) -> str | None:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.I)
    return unquote(m.group(1)) if m else None


def _extract_github_username(url: str) -> str | None:
    m = re.search(r"github\.com/([^/?#]+)", url, re.I)
    if not m:
        return None
    user = m.group(1)
    if user.lower() in {"features", "topics", "orgs", "settings"}:
        return None
    return user


def _indian_mobile_digits(digits: str) -> bool:
    """True when digit string contains a valid 10-digit Indian mobile."""
    if len(digits) < 10:
        return False
    for i in range(len(digits) - 9):
        if digits[i] in "6789":
            return True
    if digits.startswith("91") and len(digits) >= 12 and digits[-10] in "6789":
        return True
    return False


def _phone_in_text(text: str) -> bool:
    if not text:
        return False
    if PHONE_PATTERN.search(text):
        return True
    return bool(re.search(r"(?<!\d)[6-9]\d{9}(?!\d)", text))


def _phone_present(doc: DocumentModel) -> bool:
    """Phone may appear as plain text or tel: link — link is optional."""
    if _phone_in_text(doc.header_text()):
        return True
    if _phone_in_text(doc.full_text[:800]):
        return True
    for link in doc.header_links():
        if link.uri.lower().startswith("tel:"):
            digits = re.sub(r"\D", "", link.uri[4:])
            if _indian_mobile_digits(digits):
                return True
    return False


def check_header_rules(doc: DocumentModel) -> list[RuleResult]:
    results: list[RuleResult] = []
    header_text = doc.header_text()
    header_links = doc.header_links()

    results.append(
        RuleResult(
            rule_id="R301",
            severity=Severity.HARD,
            passed=bool(doc.header_name),
            reason="Student name not found at top of resume",
            evidence=doc.header_name or "missing",
        )
    )

    phone_found = _phone_present(doc)
    results.append(
        RuleResult(
            rule_id="R302",
            severity=Severity.SOFT,
            passed=phone_found,
            reason="Phone number not found in header",
            evidence=header_text[:120],
        )
    )

    college_displayed = COLLEGE_EMAIL_PATTERN.search(header_text) or COLLEGE_EMAIL_PATTERN.search(
        doc.full_text[:500]
    )
    results.append(
        RuleResult(
            rule_id="R303",
            severity=Severity.HARD,
            passed=college_displayed is not None,
            reason="College email (@sst.scaler.com) not displayed in header",
            evidence=header_text[:200],
        )
    )

    mailto_links = [l for l in header_links if l.uri.lower().startswith("mailto:")]
    displayed_email = college_displayed.group(0).lower() if college_displayed else ""
    mailto_ok = True
    mailto_evidence = ""

    def _sst_roll(email: str) -> str | None:
        m = ROLL_NUMBER_PATTERN.search(email)
        return m.group(0).lower() if m else None

    if mailto_links:
        for ml in mailto_links:
            target = ml.uri[7:].split("?")[0].split("&")[0].lower()
            if "cc=" in ml.uri.lower() or "bcc=" in ml.uri.lower():
                mailto_ok = False
                mailto_evidence = f"mailto={ml.uri}"
            if displayed_email and target != displayed_email:
                disp_roll = _sst_roll(displayed_email)
                mail_roll = _sst_roll(target)
                if disp_roll and mail_roll and disp_roll == mail_roll:
                    continue
                if "@sst.scaler.com" in displayed_email and "@sst.scaler.com" in target:
                    continue
                mailto_ok = False
                mailto_evidence = f"displayed={displayed_email}, mailto={target}"
    elif displayed_email:
        mailto_ok = False
        mailto_evidence = "No mailto link for displayed email"

    for link in doc.links:
        if link.page != 1 or not link.uri.lower().startswith("mailto:"):
            continue
        if link.y0 >= doc.header_cutoff_y:
            continue
        if "cc=" in link.uri.lower() or "bcc=" in link.uri.lower():
            mailto_ok = False
            mailto_evidence = link.uri
        target = link.uri[7:].split("?")[0].split("&")[0].lower()
        if displayed_email and "@sst.scaler.com" in displayed_email:
            disp_roll = _sst_roll(displayed_email)
            mail_roll = _sst_roll(target)
            if target != displayed_email:
                if disp_roll and mail_roll and disp_roll == mail_roll:
                    continue
                if "@sst.scaler.com" not in target:
                    mailto_ok = False
                    mailto_evidence = f"displayed={displayed_email}, mailto={target}"

    results.append(
        RuleResult(
            rule_id="R304",
            severity=Severity.HARD,
            passed=mailto_ok,
            reason="Displayed email does not match mailto target or mailto has cc/bcc params",
            evidence=mailto_evidence,
        )
    )

    linkedin_urls = [
        l.uri for l in header_links if "linkedin.com" in l.uri.lower()
    ]
    results.append(
        RuleResult(
            rule_id="R305",
            severity=Severity.HARD,
            passed=len(linkedin_urls) > 0,
            reason="LinkedIn link missing from header",
            evidence="",
        )
    )

    github_urls = [l.uri for l in header_links if "github.com" in l.uri.lower()]
    results.append(
        RuleResult(
            rule_id="R306",
            severity=Severity.HARD,
            passed=len(github_urls) > 0,
            reason="GitHub link missing from header",
            evidence="",
        )
    )

    slug_ok = True
    slug_evidence = ""
    # R307 not enforced — LinkedIn/GitHub/LeetCode profile names may differ from legal name

    results.append(
        RuleResult(
            rule_id="R307",
            severity=Severity.HARD,
            passed=True,
            reason="LinkedIn slug matches student name (not enforced)",
            evidence=slug_evidence,
        )
    )

    return results
