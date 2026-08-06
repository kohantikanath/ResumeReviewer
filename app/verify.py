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
    vanity_cache: dict[str, tuple[int | None, str]] | None = None,
) -> VerificationOutcome:
    doc = await asyncio.to_thread(extract_pdf, pdf_path)
    link_statuses: dict[str, tuple[int | None, str]] = {}

    if check_links:
        urls = _all_urls(doc)
        if urls:
            cache = url_cache if url_cache is not None else {}
            vcache = vanity_cache if vanity_cache is not None else {}
            link_statuses = await check_urls(
                urls, cache=cache, vanity_cache=vcache
            )
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
    outcome_callback: Callable[[VerificationOutcome, int, int], None] | None = None,
) -> list[VerificationOutcome]:
    metadata = load_metadata(metadata_path) if metadata_path else {}
    url_cache: dict[str, tuple[int | None, str]] = {}
    vanity_cache: dict[str, tuple[int | None, str]] = {}
    total = len(pdf_paths)
    outcomes: list[VerificationOutcome] = []

    for index, path in enumerate(pdf_paths):
        doc = await asyncio.to_thread(extract_pdf, path)
        doc_urls = _all_urls(doc)

        if check_links and doc_urls:
            if progress_callback:
                progress_callback(index, total, "links")
            await check_urls(doc_urls, cache=url_cache, vanity_cache=vanity_cache)

        per_doc_links = {
            u: url_cache[u] for u in doc_urls if u in url_cache
        }
        evaluation = _evaluate_doc(doc, metadata, per_doc_links, check_links)
        outcome = VerificationOutcome(
            path=path,
            doc=doc,
            evaluation=evaluation,
            link_statuses=per_doc_links,
        )
        outcomes.append(outcome)
        processed = index + 1
        if progress_callback:
            progress_callback(processed, total, "rules")
        if outcome_callback:
            outcome_callback(outcome, processed, total)

    return outcomes


def verify_batch(
    pdf_paths: list[Path],
    metadata_path: Path | None = None,
    check_links: bool = False,
) -> list[VerificationOutcome]:
    return asyncio.run(
        verify_batch_async(pdf_paths, metadata_path, check_links=check_links)
    )
