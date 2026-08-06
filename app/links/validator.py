"""Async HTTP link validation with per-domain limits and caching."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from app.config import (
    BOT_BLOCK_DOMAINS,
    LINK_MAX_RETRIES,
    LINK_PER_DOMAIN_CONCURRENCY,
    LINK_TIMEOUT_SEC,
)
from app.links.linkedin_ddg import (
    apply_ddg_result_to_status,
    profile_needs_ddg_fallback,
    verify_profile_via_ddg_async,
    _parse_profile_target,
)

_domain_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_semaphore(domain: str) -> asyncio.Semaphore:
    if domain not in _domain_semaphores:
        _domain_semaphores[domain] = asyncio.Semaphore(LINK_PER_DOMAIN_CONCURRENCY)
    return _domain_semaphores[domain]


def _normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def _domain(url: str) -> str:
    try:
        return (urlparse(_normalize_url(url)).hostname or "").lower()
    except Exception:
        return ""


async def _check_one(
    client: httpx.AsyncClient,
    url: str,
    cache: dict[str, tuple[int | None, str]],
) -> tuple[str, int | None, str]:
    if url in cache:
        return url, cache[url][0], cache[url][1]

    normalized = _normalize_url(url)
    domain = _domain(normalized)
    sem = _get_semaphore(domain)

    status: int | None = None
    note = "ok"

    for attempt in range(LINK_MAX_RETRIES + 1):
        try:
            async with sem:
                resp = await client.head(normalized, follow_redirects=True)
                status = resp.status_code
                if status == 405 or status >= 500:
                    resp = await client.get(normalized, follow_redirects=True)
                    status = resp.status_code
            break
        except httpx.ConnectError:
            note = "connection_refused"
            status = 0
        except httpx.TimeoutException:
            note = "timeout"
            status = None
        except Exception:
            note = "dns_failure"
            status = 0

    cache[url] = (status, note)
    return url, status, note


async def _enrich_profiles_via_ddg(
    cache: dict[str, tuple[int | None, str]],
    vanity_cache: dict[str, tuple[int | None, str]],
    urls: list[str],
) -> None:
    for url in urls:
        if url not in cache:
            continue
        status, note = cache[url]
        if not profile_needs_ddg_fallback(url, status, note):
            continue
        parsed = _parse_profile_target(url)
        if not parsed:
            continue
        site_key, vanity = parsed
        cache_key = f"{site_key}:{vanity.lower()}"
        if cache_key in vanity_cache:
            cache[url] = vanity_cache[cache_key]
            continue
        result = await verify_profile_via_ddg_async(url)
        new_entry = apply_ddg_result_to_status(result, (status, note))
        vanity_cache[cache_key] = new_entry
        cache[url] = new_entry


def _apply_bot_block_without_ddg(
    cache: dict[str, tuple[int | None, str]],
    urls: list[str],
) -> None:
    """LinkedIn/GitHub/LeetCode return 403/999 to bots — skip slow search."""
    for url in urls:
        if url not in cache:
            continue
        status, note = cache[url]
        if not profile_needs_ddg_fallback(url, status, note):
            continue
        domain = _domain(url)
        if domain in BOT_BLOCK_DOMAINS and status in (403, 429, 999):
            cache[url] = (403, "profile_bot_block_unverified")


async def check_urls(
    urls: list[str],
    cache: dict[str, tuple[int | None, str]] | None = None,
    vanity_cache: dict[str, tuple[int | None, str]] | None = None,
    *,
    use_ddg_linkedin: bool = True,
) -> dict[str, tuple[int | None, str]]:
    if cache is None:
        cache = {}
    if vanity_cache is None:
        vanity_cache = {}

    unique = [u for u in urls if u not in cache]
    if unique:
        async with httpx.AsyncClient(
            timeout=LINK_TIMEOUT_SEC,
            headers={"User-Agent": "ResumeVerify/1.0"},
        ) as client:
            tasks = [_check_one(client, url, cache) for url in unique]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item in results:
                if isinstance(item, tuple):
                    url, status, note = item
                    cache[url] = (status, note)

    _apply_bot_block_without_ddg(cache, urls)

    if use_ddg_linkedin:
        await _enrich_profiles_via_ddg(cache, vanity_cache, urls)

    return cache


def classify_url(url: str, status: int | None, note: str) -> str:
    domain = _domain(url)
    if status in (200, 201, 204, 301, 302, 303, 307, 308):
        return "pass"
    if status == 404 or note in ("dns_failure", "connection_refused"):
        if domain in BOT_BLOCK_DOMAINS:
            return "soft"
        return "hard_fail"
    if status in (403, 429, 999) or note == "timeout":
        return "soft"
    if status and 400 <= status < 500:
        if domain in BOT_BLOCK_DOMAINS:
            return "soft"
        return "hard_fail"
    return "unknown"
