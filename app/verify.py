"""End-to-end resume verification pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from app.extract.pdf_loader import derive_metadata, extract_pdf
from app.links.validator import check_urls
from app.metadata import load_metadata, match_metadata_row
from app.models import DocumentModel
from app.rules.base import EvaluationResult, run_all_rules
from app.rules.link_rules import _all_urls, network_link_results
from app.types import VerificationOutcome


def _evaluate_doc(
    doc: DocumentModel,
    metadata: dict[str, dict] | None,
    link_statuses: dict[str, tuple[int | None, str]],
    check_links: bool,
) -> EvaluationResult:
    derived = derive_metadata(doc)
    meta_row = None
    if metadata:
        meta_row = match_metadata_row(
            derived.get("Roll Number", ""),
            metadata,
            derived,
        )

    link_rule_results = []
    if check_links and link_statuses:
        link_rule_results = network_link_results(doc, link_statuses)

    return run_all_rules(doc, meta_row, link_rule_results)


async def verify_pdf_async(
    pdf_path: Path,
    metadata: dict[str, dict] | None = None,
    check_links: bool = True,
    url_cache: dict[str, tuple[int | None, str]] | None = None,
) -> VerificationOutcome:
    doc = extract_pdf(pdf_path)
    link_statuses: dict[str, tuple[int | None, str]] = {}

    if check_links:
        urls = _all_urls(doc)
        if urls:
            cache = url_cache if url_cache is not None else {}
            link_statuses = await check_urls(urls, cache=cache)
            if url_cache is not None:
                url_cache.update(link_statuses)

    evaluation = _evaluate_doc(doc, metadata, link_statuses, check_links)
    return VerificationOutcome(
        path=pdf_path,
        doc=doc,
        evaluation=evaluation,
        link_statuses=link_statuses,
    )


def verify_pdf(
    pdf_path: Path,
    metadata: dict[str, dict] | None = None,
    check_links: bool = False,
) -> VerificationOutcome:
    return asyncio.run(verify_pdf_async(pdf_path, metadata, check_links))


async def verify_batch_async(
    pdf_paths: list[Path],
    metadata_path: Path | None = None,
    check_links: bool = True,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[VerificationOutcome]:
    metadata = load_metadata(metadata_path) if metadata_path else {}
    url_cache: dict[str, tuple[int | None, str]] = {}

    if check_links:
        all_urls: list[str] = []
        for path in pdf_paths:
            doc = extract_pdf(path)
            all_urls.extend(_all_urls(doc))
        unique_urls = list(dict.fromkeys(all_urls))
        if unique_urls:
            await check_urls(unique_urls, cache=url_cache)

    outcomes: list[VerificationOutcome] = []
    total = len(pdf_paths)

    for index, path in enumerate(pdf_paths):
        doc = extract_pdf(path)
        per_doc_links = {
            u: url_cache[u] for u in _all_urls(doc) if u in url_cache
        }
        evaluation = _evaluate_doc(doc, metadata, per_doc_links, check_links)
        outcomes.append(
            VerificationOutcome(
                path=path,
                doc=doc,
                evaluation=evaluation,
                link_statuses=per_doc_links,
            )
        )
        if progress_callback:
            progress_callback(index + 1, total, "rules")

    return outcomes


def verify_batch(
    pdf_paths: list[Path],
    metadata_path: Path | None = None,
    check_links: bool = False,
) -> list[VerificationOutcome]:
    return asyncio.run(
        verify_batch_async(pdf_paths, metadata_path, check_links=check_links)
    )
