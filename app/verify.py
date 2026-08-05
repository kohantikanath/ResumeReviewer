"""End-to-end resume verification pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.extract.pdf_loader import derive_metadata, extract_pdf
from app.links.validator import check_urls
from app.metadata import load_metadata, match_metadata_row
from app.models import DocumentModel
from app.rules.base import EvaluationResult, run_all_rules
from app.rules.link_rules import _all_urls, network_link_results


async def verify_pdf_async(
    pdf_path: Path,
    metadata: dict[str, dict] | None = None,
    check_links: bool = True,
) -> tuple[DocumentModel, EvaluationResult, dict[str, tuple[int | None, str]]]:
    doc = extract_pdf(pdf_path)
    derived = derive_metadata(doc)
    meta_row = None
    if metadata:
        meta_row = match_metadata_row(
            derived.get("Roll Number", ""),
            metadata,
            derived,
        )

    link_statuses: dict[str, tuple[int | None, str]] = {}
    link_rule_results = []

    if check_links:
        urls = _all_urls(doc)
        if urls:
            link_statuses = await check_urls(urls)
            link_rule_results = network_link_results(doc, link_statuses)

    evaluation = run_all_rules(doc, meta_row, link_rule_results)
    return doc, evaluation, link_statuses


def verify_pdf(
    pdf_path: Path,
    metadata: dict[str, dict] | None = None,
    check_links: bool = False,
) -> tuple[DocumentModel, EvaluationResult, dict[str, tuple[int | None, str]]]:
    return asyncio.run(verify_pdf_async(pdf_path, metadata, check_links))


def verify_batch(
    pdf_paths: list[Path],
    metadata_path: Path | None = None,
    check_links: bool = False,
) -> list[tuple[Path, DocumentModel, EvaluationResult]]:
    metadata = load_metadata(metadata_path) if metadata_path else {}
    results = []
    for path in pdf_paths:
        doc, evaluation, _ = verify_pdf(path, metadata, check_links=check_links)
        results.append((path, doc, evaluation))
    return results
