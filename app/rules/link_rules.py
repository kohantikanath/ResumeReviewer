"""R5xx link rules (static + network)."""

import re
from urllib.parse import urlparse

from app.config import BOT_BLOCK_DOMAINS, PLACEHOLDER_URL_PATTERNS, UTM_PATTERN
from app.extract.link_locate import find_link_for_url, format_link_location
from app.models import DocumentModel
from app.rules.base import RuleResult, Severity


def _extract_github_username(url: str) -> str | None:
    m = re.search(r"github\.com/([^/?#]+)", url, re.I)
    if not m:
        return None
    user = m.group(1)
    if user.lower() in {"features", "topics", "orgs", "settings"}:
        return None
    return user.lower()


def _all_urls(doc: DocumentModel) -> list[str]:
    urls = [
        l.uri
        for l in doc.links
        if l.uri and not l.uri.startswith("mailto:") and not l.uri.startswith("tel:")
    ]
    return list(dict.fromkeys(urls))


def _domain(url: str) -> str:
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def _url_with_location(doc: DocumentModel, url: str, detail: str) -> str:
    link = find_link_for_url(doc, url)
    if link:
        loc = format_link_location(doc, link)
        return f"{url} ({detail}) [{loc}]"
    return f"{url} ({detail})"


def check_static_link_rules(doc: DocumentModel) -> list[RuleResult]:
    results: list[RuleResult] = []
    urls = _all_urls(doc)

    placeholder_fail = False
    placeholder_evidence = ""
    placeholder_hits: list[str] = []
    for url in urls:
        for pattern in PLACEHOLDER_URL_PATTERNS:
            if pattern.search(url):
                placeholder_fail = True
                placeholder_hits.append(_url_with_location(doc, url, "placeholder"))
                break

    results.append(
        RuleResult(
            rule_id="R501",
            severity=Severity.HARD,
            passed=not placeholder_fail,
            reason="Malformed or placeholder URL found",
            evidence="; ".join(placeholder_hits[:5]),
        )
    )

    utm_found = [u for u in urls if UTM_PATTERN.search(u)]
    utm_evidence = "; ".join(_url_with_location(doc, u, "utm") for u in utm_found[:5])
    results.append(
        RuleResult(
            rule_id="R505",
            severity=Severity.SOFT,
            passed=len(utm_found) == 0,
            reason="Tracking parameters (utm_*) in URLs",
            evidence=utm_evidence,
        )
    )

    header_github = None
    for link in doc.header_links():
        if "github.com" in link.uri.lower():
            header_github = _extract_github_username(link.uri)
            break

    github_ok = True
    github_evidence = ""
    if header_github:
        project_github_urls = [
            u for u in urls if "github.com" in u.lower() and "/in/" not in u.lower()
        ]
        mismatches: list[str] = []
        for url in project_github_urls:
            user = _extract_github_username(url)
            if user and user != header_github:
                parts = url.lower().split("github.com/")
                if len(parts) > 1 and "/" in parts[1]:
                    if user != header_github:
                        github_ok = False
                        mismatches.append(_url_with_location(doc, url, f"user={user}"))
        github_evidence = "; ".join(mismatches[:5])

    results.append(
        RuleResult(
            rule_id="R504",
            severity=Severity.HARD,
            passed=github_ok,
            reason="GitHub username in header does not match project repo links",
            evidence=github_evidence,
        )
    )

    return results


def network_link_results(
    doc: DocumentModel,
    url_statuses: dict[str, tuple[int | None, str]],
) -> list[RuleResult]:
    """Build R502/R503 from pre-fetched URL status map."""
    urls = _all_urls(doc)
    hard_failures: list[str] = []
    soft_failures: list[str] = []

    for url in urls:
        status, note = url_statuses.get(url, (None, "not checked"))
        domain = _domain(url)

        if status is None:
            continue

        detail = str(note or status)
        located = _url_with_location(doc, url, detail)

        if status in (404, 0) or note in ("dns_failure", "connection_refused"):
            if domain in BOT_BLOCK_DOMAINS and status in (403, 429, 999):
                soft_failures.append(located)
            else:
                hard_failures.append(located)
        elif status in (403, 429, 999) or note == "timeout":
            if domain in BOT_BLOCK_DOMAINS or status in (403, 429, 999):
                soft_failures.append(located)
            else:
                hard_failures.append(located)

    return [
        RuleResult(
            rule_id="R502",
            severity=Severity.HARD,
            passed=not hard_failures,
            reason="Broken link (404, DNS failure, or connection refused)",
            evidence="; ".join(hard_failures[:8]),
        ),
        RuleResult(
            rule_id="R503",
            severity=Severity.SOFT,
            passed=not soft_failures,
            reason="Link unverifiable due to bot-blocking or timeout — check manually",
            evidence="; ".join(soft_failures[:8]),
        ),
    ]
