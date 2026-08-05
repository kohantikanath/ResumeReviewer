"""Locate hyperlinks in PDF text for reports."""

from __future__ import annotations

from app.models import DocumentModel, LinkAnnotation


def describe_link_location(doc: DocumentModel, link: LinkAnnotation) -> tuple[int, str, str]:
    """Return approximate line number (page order), section title, nearby anchor text."""
    page_spans = sorted(
        [s for s in doc.spans if s.page == link.page],
        key=lambda s: (s.y0, s.x0),
    )

    section_title = "Header"
    if link.page == 1 and link.y0 >= doc.header_cutoff_y:
        current = "Header"
        for section in doc.sections:
            if section.y0 <= link.y0:
                current = section.title
        section_title = current

    line_no = 0
    anchor = ""
    for i, span in enumerate(page_spans):
        if span.y0 - 8 <= link.y0 <= span.y1 + 8:
            line_no = i + 1
            anchor = span.text.strip()
            break

    if not anchor and page_spans:
        closest = min(page_spans, key=lambda s: abs(s.y0 - link.y0))
        line_no = page_spans.index(closest) + 1
        anchor = closest.text.strip()

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
    mapping: dict[str, str] = {}
    for link in doc.links:
        if not link.uri or link.uri.startswith(("mailto:", "tel:")):
            continue
        loc = format_link_location(doc, link)
        if link.uri not in mapping:
            mapping[link.uri] = loc
    return mapping


def find_link_for_url(doc: DocumentModel, url: str) -> LinkAnnotation | None:
    for link in doc.links:
        if link.uri == url:
            return link
    return None
