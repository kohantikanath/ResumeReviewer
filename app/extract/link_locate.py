"""Locate hyperlinks in PDF text for reports."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.models import DocumentModel, LinkAnnotation


def _section_for_link(doc: DocumentModel, link: LinkAnnotation) -> str:
    if link.page == 1 and link.y0 < doc.header_cutoff_y:
        return "Header"
    current = "Header"
    for section in doc.sections:
        if section.y0 <= link.y0:
            current = section.title
    return current


def _spans_on_line(page_spans: list, link: LinkAnnotation) -> list:
    return [
        s
        for s in page_spans
        if s.y0 - 8 <= link.y0 <= s.y1 + 8
    ]


def _anchor_for_link(page_spans: list, link: LinkAnnotation) -> tuple[int, str]:
    """Pick anchor text closest to this link's x-position (not the whole line)."""
    line_spans = _spans_on_line(page_spans, link)
    if not line_spans:
        closest = min(page_spans, key=lambda s: abs(s.y0 - link.y0))
        line_spans = [closest]

    line_no = 0
    for i, span in enumerate(page_spans):
        if span in line_spans or (
            span.y0 - 8 <= link.y0 <= span.y1 + 8
        ):
            line_no = i + 1
            break

    link_mid = (link.x0 + link.x1) / 2

    overlapping = [
        s for s in line_spans
        if s.x0 <= link.x1 + 4 and s.x1 >= link.x0 - 4
    ]
    if overlapping:
        anchor_span = min(overlapping, key=lambda s: abs((s.x0 + s.x1) / 2 - link_mid))
        return line_no, anchor_span.text.strip()

    left_spans = [s for s in line_spans if s.x1 <= link.x0 + 6]
    if left_spans:
        anchor_span = max(left_spans, key=lambda s: s.x1)
        label = anchor_span.text.strip()
        if "|" in label:
            segments = [seg.strip() for seg in label.split("|")]
            return line_no, segments[-1] if segments else label
        return line_no, label

    try:
        host = urlparse(link.uri).hostname or ""
        label = host.replace("www.", "") if host else link.uri
    except Exception:
        label = link.uri
    return line_no, label


def describe_link_location(doc: DocumentModel, link: LinkAnnotation) -> tuple[int, str, str]:
    """Return line number, section title, and per-link anchor text."""
    page_spans = sorted(
        [s for s in doc.spans if s.page == link.page],
        key=lambda s: (s.y0, s.x0),
    )
    section_title = _section_for_link(doc, link)
    line_no, anchor = _anchor_for_link(page_spans, link)
    return line_no, section_title, anchor


def format_link_location(doc: DocumentModel, link: LinkAnnotation) -> str:
    line_no, section, anchor = describe_link_location(doc, link)
    parts = []
    if line_no:
        parts.append(f"line {line_no}")
    if section:
        parts.append(section)
    if anchor:
        parts.append(f'"{anchor[:50]}"')
    return ", ".join(parts)


def build_link_location_map(doc: DocumentModel) -> dict[str, str]:
    """Map URL -> human-readable location string."""
    return {
        url: _format_location_tuple(*detail)
        for url, detail in build_link_location_details(doc).items()
    }


def _format_location_tuple(line_no: int, section: str, anchor: str, page: int) -> str:
    parts = []
    if line_no:
        parts.append(f"line {line_no}")
    if section:
        parts.append(section)
    if anchor:
        parts.append(f'"{anchor[:50]}"')
    if page:
        parts.append(f"page {page}")
    return ", ".join(parts)


def build_link_location_details(
    doc: DocumentModel,
) -> dict[str, tuple[int, str, str, int]]:
    """Map URL -> (line_no, section, anchor, page). One entry per link annotation."""
    mapping: dict[str, tuple[int, str, str, int]] = {}
    for link in doc.links:
        if not link.uri or link.uri.startswith(("mailto:", "tel:")):
            continue
        line_no, section, anchor = describe_link_location(doc, link)
        key = _link_key(link.uri, link.page, link.x0, link.y0)
        mapping[key] = (line_no, section, anchor, link.page)
        if link.uri not in mapping:
            mapping[link.uri] = (line_no, section, anchor, link.page)
    return mapping


def _link_key(uri: str, page: int, x0: float, y0: float) -> str:
    return f"{uri}@{page}:{x0:.1f}:{y0:.1f}"


def format_failed_link_summary(
    url: str,
    status: int | None,
    note: str,
    line_no: int,
    section: str,
    anchor: str,
    page: int,
) -> str:
    failure = (note or "").strip()
    if not failure or failure == "ok":
        failure = str(status) if status is not None else "failed"
    location_parts = []
    if line_no:
        location_parts.append(f"Line {line_no}")
    if page:
        location_parts.append(f"Page {page}")
    if section:
        location_parts.append(section)
    location = " | ".join(location_parts) if location_parts else "Unknown location"
    label = f'"{anchor}"' if anchor else "link"
    return (
        f"URL {url} returned {failure} at {location}, anchor text {label}"
    )


def find_link_for_url(doc: DocumentModel, url: str) -> LinkAnnotation | None:
    matches = [link for link in doc.links if link.uri == url]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return matches[0]


def find_best_link_for_url(
    doc: DocumentModel,
    url: str,
    failed_status: int | None,
) -> LinkAnnotation | None:
    """When multiple annotations share a URL, prefer the one whose anchor matches URL host."""
    matches = [link for link in doc.links if link.uri == url]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    host = (urlparse(url).hostname or "").lower().replace("www.", "")
    scored: list[tuple[int, LinkAnnotation]] = []
    for link in matches:
        _, _, anchor = describe_link_location(doc, link)
        anchor_l = anchor.lower()
        score = 0
        if host and host.split(".")[0] in anchor_l:
            score += 2
        if "github" in host and "github" in anchor_l:
            score += 3
        if "linkedin" in host and "linkedin" in anchor_l:
            score += 3
        scored.append((score, link))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]
