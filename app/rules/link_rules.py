"""R5xx link rules (static + network)."""

import re
from urllib.parse import urlparse

from app.config import BOT_BLOCK_DOMAINS, PLACEHOLDER_URL_PATTERNS, UTM_PATTERN
from app.extract.link_locate import describe_link_location, find_best_link_for_url
from app.models import DocumentModel
from app.rules.base import RuleResult, Severity


def _is_placeholder_url(url: str) -> bool:
    return any(pattern.search(url) for pattern in PLACEHOLDER_URL_PATTERNS)


def _all_urls(doc: DocumentModel) -> list[str]:
    urls = [
        l.uri
        for l in doc.links
        if l.uri and not l.uri.startswith("mailto:") and not l.uri.startswith("tel:")
    ]
    return list(dict.fromkeys(urls))


def checkable_urls(doc: DocumentModel) -> list[str]:
    """URLs worth network validation — skips placeholders (R501 covers those)."""
    return [u for u in _all_urls(doc) if not _is_placeholder_url(u)]


def _domain(url: str) -> str:
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def _failure_explanation(
    url: str,
    status: int | None,
    note: str,
    domain: str,
) -> str:
    if note.startswith("ddg:valid"):
        return "verified via DuckDuckGo search index (site blocks direct bots)"
    if note == "profile_bot_block_unverified":
        return (
            "site blocks automated checks (HTTP 403); profile may still open in a browser — "
            "could not confirm via search index"
        )
    if note == "ddg_not_indexed":
        return "not found in search indexes — likely broken or private profile"
    if domain in BOT_BLOCK_DOMAINS and status in (403, 429, 999):
        return (
            f"automated check got HTTP {status} — {domain} blocks bots; "
            "the profile usually still opens in a normal browser"
        )
    if note == "timeout":
        return "request timed out — site may be slow or blocking automated checks"
    if note in ("dns_failure", "connection_refused"):
        return f"{note.replace('_', ' ')} — host may be down or URL is wrong"
    if status == 404:
        return (
            "HTTP 404 Not Found — server says this exact URL does not exist "
            "(open this URL in your browser to confirm)"
        )
    if status == 0:
        return "could not connect to the server"
    if status:
        return f"HTTP {status}"
    return note or "failed"


def _link_failure_reason(
    doc: DocumentModel,
    url: str,
    status: int | None,
    note: str,
) -> str:
    link = find_best_link_for_url(doc, url, status)
    domain = _domain(url)
    failure = _failure_explanation(url, status, note, domain)
    if link:
        line_no, section, anchor = describe_link_location(doc, link)
        loc_parts = []
        if line_no:
            loc_parts.append(f"Line {line_no}")
        if section:
            loc_parts.append(section)
        loc = " | ".join(loc_parts) if loc_parts else "unknown location"
        label = f'"{anchor}"' if anchor else "link"
        return f"URL {url} — {failure} at {loc}, anchor text {label}"
    return f"URL {url} — {failure}"


def check_static_link_rules(doc: DocumentModel) -> list[RuleResult]:
    results: list[RuleResult] = []
    urls = _all_urls(doc)

    placeholder_hits: list[str] = []
    for url in urls:
        if _is_placeholder_url(url):
            placeholder_hits.append(_link_failure_reason(doc, url, None, "placeholder"))

    results.append(
        RuleResult(
            rule_id="R501",
            severity=Severity.HARD,
            passed=not placeholder_hits,
            reason="Malformed or placeholder URL found",
            evidence="; ".join(placeholder_hits[:5]),
        )
    )

    utm_found = [u for u in urls if UTM_PATTERN.search(u)]
    utm_evidence = "; ".join(
        _link_failure_reason(doc, u, None, "utm tracking params") for u in utm_found[:5]
    )
    results.append(
        RuleResult(
            rule_id="R505",
            severity=Severity.SOFT,
            passed=len(utm_found) == 0,
            reason="Tracking parameters (utm_*) in URLs",
            evidence=utm_evidence,
        )
    )

    # R504 disabled — GitHub/LeetCode/LinkedIn handles may differ from student name
    results.append(
        RuleResult(
            rule_id="R504",
            severity=Severity.HARD,
            passed=True,
            reason="GitHub username consistency (not enforced)",
            evidence="",
        )
    )

    return results


def network_link_results(
    doc: DocumentModel,
    url_statuses: dict[str, tuple[int | None, str]],
) -> list[RuleResult]:
    """One RuleResult per failed URL so reports cite the exact broken link."""
    urls = _all_urls(doc)
    results: list[RuleResult] = []
    hard_count = 0
    soft_count = 0

    for url in urls:
        if _is_placeholder_url(url):
            continue

        status, note = url_statuses.get(url, (None, "not checked"))
        domain = _domain(url)

        if status is None:
            continue

        is_hard = False
        is_soft = False

        if status in (404, 0) or note in ("dns_failure", "connection_refused"):
            if domain in BOT_BLOCK_DOMAINS and status in (403, 429, 999):
                is_soft = True
            elif note == "ddg_not_indexed":
                is_hard = True
            else:
                is_hard = True
        elif note.startswith("ddg:valid"):
            continue
        elif note == "profile_bot_block_unverified":
            # Bot-blocked profile host; link often works in a browser — not broken
            continue
        elif note == "ddg_not_indexed":
            is_hard = True
        elif status in (403, 429, 999) or note == "timeout":
            if domain in BOT_BLOCK_DOMAINS or status in (403, 429, 999):
                is_soft = True
            else:
                is_hard = True

        if not is_hard and not is_soft:
            continue

        reason_text = _link_failure_reason(doc, url, status, note)
        if is_hard:
            hard_count += 1
            results.append(
                RuleResult(
                    rule_id="R502",
                    severity=Severity.HARD,
                    passed=False,
                    reason="Broken hyperlink",
                    evidence=reason_text,
                )
            )
        else:
            soft_count += 1
            results.append(
                RuleResult(
                    rule_id="R503",
                    severity=Severity.SOFT,
                    passed=False,
                    reason="Unverifiable hyperlink",
                    evidence=reason_text,
                )
            )

    if hard_count == 0:
        results.insert(
            0,
            RuleResult(
                rule_id="R502",
                severity=Severity.HARD,
                passed=True,
                reason="Broken hyperlink",
                evidence="",
            ),
        )
    if soft_count == 0:
        results.append(
            RuleResult(
                rule_id="R503",
                severity=Severity.SOFT,
                passed=True,
                reason="Unverifiable hyperlink",
                evidence="",
            ),
        )

    return results
