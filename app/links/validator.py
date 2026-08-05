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


async def check_urls(
    urls: list[str],
    cache: dict[str, tuple[int | None, str]] | None = None,
) -> dict[str, tuple[int | None, str]]:
    if cache is None:
        cache = {}
    unique = [u for u in urls if u not in cache]
    if not unique:
        return cache

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
