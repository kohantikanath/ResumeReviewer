"""Verify profile URLs via DuckDuckGo when direct HTTP checks fail (bot blocks)."""

from __future__ import annotations

import asyncio
import random
import re

from ddgs import DDGS

DDG_MIN_DELAY_SEC = 2.0
DDG_MAX_DELAY_SEC = 4.5

LINKEDIN_VANITY_RE = re.compile(r"linkedin\.com/in/([^/?#\s]+)", re.IGNORECASE)
GITHUB_VANITY_RE = re.compile(r"github\.com/([^/?#\s]+)", re.IGNORECASE)
LEETCODE_VANITY_RE = re.compile(r"leetcode\.com/(?:u/)?([^/?#\s]+)", re.IGNORECASE)

GITHUB_RESERVED = frozenset(
    {
        "about",
        "apps",
        "collections",
        "contact",
        "customer-stories",
        "enterprise",
        "features",
        "login",
        "marketplace",
        "new",
        "notifications",
        "orgs",
        "pricing",
        "search",
        "settings",
        "signup",
        "sponsors",
        "topics",
        "trending",
    }
)


class ProfileDDGResult:
    __slots__ = ("status", "details")

    def __init__(self, status: str, details: str) -> None:
        self.status = status
        self.details = details


def extract_linkedin_vanity(profile_url: str) -> str | None:
    match = LINKEDIN_VANITY_RE.search(profile_url or "")
    return match.group(1).strip() if match else None


def _parse_profile_target(url: str) -> tuple[str, str] | None:
    """Return (site_key, vanity_id) for supported profile hosts."""
    lower = (url or "").lower()
    if "linkedin.com" in lower:
        vanity = extract_linkedin_vanity(url)
        return ("linkedin", vanity) if vanity else None
    if "github.com" in lower:
        match = GITHUB_VANITY_RE.search(url)
        if match:
            vanity = match.group(1).strip()
            if vanity.lower() not in GITHUB_RESERVED:
                return ("github", vanity)
    if "leetcode.com" in lower:
        match = LEETCODE_VANITY_RE.search(url)
        if match:
            vanity = match.group(1).strip()
            if vanity.lower() not in {"explore", "problemset", "contest"}:
                return ("leetcode", vanity)
    return None


def _ddg_queries(site_key: str, vanity_id: str) -> list[str]:
    if site_key == "linkedin":
        return [f"site:linkedin.com/in/{vanity_id}"]
    if site_key == "github":
        return [f"site:github.com/{vanity_id}", f"{vanity_id} site:github.com"]
    return [
        f"site:leetcode.com/u/{vanity_id}",
        f"leetcode.com/u/{vanity_id}",
        f"{vanity_id} site:leetcode.com",
    ]


def _href_matches(site_key: str, vanity_id: str, href: str) -> bool:
    href_lower = href.lower()
    vanity_lower = vanity_id.lower()
    if site_key == "linkedin":
        return vanity_lower in href_lower and "/in/" in href_lower
    if site_key == "github":
        return (
            "github.com" in href_lower
            and re.search(
                rf"github\.com/{re.escape(vanity_lower)}(?:/|$|\?)",
                href_lower,
            )
        )
    # LeetCode profiles use /u/{username}
    return bool(
        re.search(
            rf"leetcode\.com/u/{re.escape(vanity_lower)}(?:/|$|\?)",
            href_lower,
        )
    )


def _profile_indexed(site_key: str, vanity_id: str) -> bool:
    for query in _ddg_queries(site_key, vanity_id):
        try:
            results = list(DDGS().text(query, max_results=12))
        except Exception:
            continue
        for item in results:
            href = item.get("href") or ""
            if _href_matches(site_key, vanity_id, href):
                return True
    return False


def verify_profile_via_ddg(profile_url: str) -> ProfileDDGResult:
    """
    Check whether a profile URL appears in search indexes.
    Does not compare names to metadata — existence only.
    """
    parsed = _parse_profile_target(profile_url)
    if not parsed:
        return ProfileDDGResult("INVALID_URL", "Not a supported profile URL")

    site_key, vanity_id = parsed
    if _profile_indexed(site_key, vanity_id):
        return ProfileDDGResult(
            "VALID",
            f"Profile indexed on {site_key} ({vanity_id})",
        )
    return ProfileDDGResult(
        "BROKEN_OR_PRIVATE",
        "Profile not found in search indexes (likely 404 or private)",
    )


async def verify_profile_via_ddg_async(profile_url: str) -> ProfileDDGResult:
    await asyncio.sleep(random.uniform(DDG_MIN_DELAY_SEC, DDG_MAX_DELAY_SEC))
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(verify_profile_via_ddg, profile_url),
            timeout=25.0,
        )
    except asyncio.TimeoutError:
        return ProfileDDGResult("BROKEN_OR_PRIVATE", "DuckDuckGo search timed out")


def profile_needs_ddg_fallback(url: str, status: int | None, note: str) -> bool:
    """Use DDG when direct HTTP could not confirm the link (bot block, timeout, etc.)."""
    if _parse_profile_target(url) is None:
        return False
    if note.startswith("ddg:") or note == "profile_bot_block_unverified":
        return False
    if status in (200, 201, 204, 301, 302, 303, 307, 308):
        return False
    return True


def apply_ddg_result_to_status(
    result: ProfileDDGResult,
    prior: tuple[int | None, str],
) -> tuple[int | None, str]:
    prior_status, prior_note = prior
    if result.status == "VALID":
        return (200, "ddg:valid")
    if result.status == "BROKEN_OR_PRIVATE":
        # Site blocked bots (403) but search can't confirm — soft unverifiable, not broken
        if prior_status in (403, 429, 999) or prior_note == "timeout":
            return (403, "profile_bot_block_unverified")
        return (404, "ddg_not_indexed")
    return prior_status, f"ddg:{result.status.lower()}"


# Backward-compatible aliases for scripts/tests
LinkedInDDGResult = ProfileDDGResult


def verify_linkedin_via_ddg(profile_url: str, expected_name: str | None = None) -> ProfileDDGResult:
    """CLI helper — name argument ignored; only checks link exists."""
    return verify_profile_via_ddg(profile_url)


async def verify_linkedin_via_ddg_async(
    profile_url: str,
    expected_name: str | None = None,
) -> ProfileDDGResult:
    return await verify_profile_via_ddg_async(profile_url)


def linkedin_needs_ddg_fallback(url: str, status: int | None, note: str) -> bool:
    return profile_needs_ddg_fallback(url, status, note)
