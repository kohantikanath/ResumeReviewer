"""PDF extraction: spans, links, images, sections."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from statistics import mode

import fitz

from app.config import ROLL_NUMBER_PATTERN, SECTION_ALIASES, SECTION_FONT_MULTIPLIER
from app.models import (
    DocumentModel,
    ExperienceEntry,
    LinkAnnotation,
    ProjectEntry,
    Section,
    TextSpan,
)

BULLET_RE = re.compile(r"^[\u2022\u2013\u2014\-•]\s+|^\d+\.\s+|^–\s+")
TECH_LINE_RE = re.compile(r"^tech\s*:", re.IGNORECASE)
DATE_RE = re.compile(
    r"\d{4}|present|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec",
    re.IGNORECASE,
)


def _is_wrapped_line(line: str) -> bool:
    if not line:
        return False
    if line[0].islower():
        return True
    prefixes = ("and ", "with ", "using ", "to ", "for ", "by ", "via ", "plus ", "over ")
    if any(line.startswith(p) for p in prefixes):
        return True
    if len(line.split()) <= 4 and line.endswith("."):
        return True
    return False


LOCATION_WORDS = frozenset(
    {
        "india",
        "remote",
        "bengaluru",
        "bangalore",
        "pilani",
        "delhi",
        "mumbai",
        "hyderabad",
        "chennai",
        "pune",
    }
)


def _is_likely_new_experience_header(line: str) -> bool:
    if BULLET_RE.match(line):
        return False
    lower = line.lower().strip()
    if lower in LOCATION_WORDS or len(line.split()) == 1:
        return False
    if DATE_RE.search(line):
        return True
    lower = line.lower()
    if any(kw in lower for kw in ("intern", "engineer", "developer", "analyst")):
        return len(line.split()) <= 12
    words = line.split()
    if len(words) <= 5 and line[0].isupper() and "|" not in line:
        return not line.endswith(".")
    return False


def _is_likely_new_project_header(line: str) -> bool:
    if BULLET_RE.match(line) or TECH_LINE_RE.match(line):
        return False
    if "|" in line or "github" in line.lower() or "website" in line.lower():
        return True
    if DATE_RE.search(line) and len(line.split()) <= 10:
        return True
    words = line.split()
    return len(words) <= 8 and line[0].isupper() and not _is_wrapped_line(line)


def _normalize_section_title(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _match_section_key(text: str) -> str | None:
    normalized = _normalize_section_title(text)
    for key, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if normalized == alias or normalized.startswith(alias):
                return key
    return None


def _compute_modal_font(sizes: list[float]) -> float:
    if not sizes:
        return 9.0
    try:
        return float(mode(sizes))
    except Exception:
        counts = Counter(sizes)
        return float(counts.most_common(1)[0][0])


def _extract_spans(page: fitz.Page, page_num: int) -> list[TextSpan]:
    """Extract line-level text spans (words merged per visual line)."""
    spans: list[TextSpan] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            parts: list[str] = []
            sizes: list[float] = []
            x0, y0, x1, y1 = 0.0, 0.0, 0.0, 0.0
            for sp in line["spans"]:
                text = sp["text"].strip()
                if not text:
                    continue
                parts.append(text)
                sizes.append(sp["size"])
                bx = sp["bbox"]
                if not parts or len(parts) == 1:
                    x0, y0, x1, y1 = bx[0], bx[1], bx[2], bx[3]
                else:
                    x0 = min(x0, bx[0])
                    y0 = min(y0, bx[1])
                    x1 = max(x1, bx[2])
                    y1 = max(y1, bx[3])
            if parts:
                spans.append(
                    TextSpan(
                        text=" ".join(parts),
                        size=round(max(sizes), 1),
                        x0=x0,
                        y0=y0,
                        x1=x1,
                        y1=y1,
                        page=page_num,
                    )
                )
    return spans


def _extract_links(page: fitz.Page, page_num: int) -> list[LinkAnnotation]:
    links: list[LinkAnnotation] = []
    for link in page.get_links():
        uri = link.get("uri") or ""
        rect = link.get("from")
        if not rect:
            continue
        links.append(
            LinkAnnotation(
                uri=uri,
                page=page_num,
                x0=rect.x0,
                y0=rect.y0,
                x1=rect.x1,
                y1=rect.y1,
                kind=link.get("kind", 0),
            )
        )
    return links


def _find_section_headers(page1: list[TextSpan], modal_size: float) -> list[tuple[str, str, float]]:
    threshold = modal_size * SECTION_FONT_MULTIPLIER
    headers: list[tuple[str, str, float]] = []
    for span in page1:
        if span.size < threshold:
            continue
        key = _match_section_key(span.text)
        if key:
            headers.append((key, span.text.strip(), span.y0))
    headers.sort(key=lambda h: h[2])
    return headers


def _detect_header(page1: list[TextSpan], modal_size: float, section_headers: list[tuple[str, str, float]]) -> tuple[str, list[TextSpan], float]:
    header_cutoff = section_headers[0][2] if section_headers else 200.0
    header_spans = [s for s in page1 if s.y0 < header_cutoff]

    name_candidates = [
        s for s in header_spans
        if s.size > modal_size * 1.2 and not _match_section_key(s.text)
    ]
    if name_candidates:
        max_size = max(s.size for s in name_candidates)
        name_parts = [
            s.text
            for s in sorted(name_candidates, key=lambda s: s.y0)
            if s.size >= max_size - 1.0
        ]
        name = " ".join(name_parts)
    else:
        name = header_spans[0].text if header_spans else ""

    return name.strip(), header_spans, header_cutoff


def _split_sections(
    page1: list[TextSpan],
    modal_size: float,
    section_headers: list[tuple[str, str, float]],
) -> list[Section]:
    threshold = modal_size * SECTION_FONT_MULTIPLIER
    if not section_headers:
        return []

    sections: list[Section] = []
    for idx, (key, title, y0) in enumerate(section_headers):
        y_end = section_headers[idx + 1][2] if idx + 1 < len(section_headers) else 9999.0
        body_spans = [
            s for s in page1
            if y0 <= s.y0 < y_end
            and not (_match_section_key(s.text) and s.size >= threshold and s.y0 == y0)
        ]
        text = "\n".join(s.text for s in body_spans)
        sections.append(Section(key=key, title=title, spans=body_spans, text=text, y0=y0))

    return sections


def _parse_project_entries(section: Section, doc_links: list[LinkAnnotation]) -> list[ProjectEntry]:
    lines = section.text.splitlines()
    entries: list[ProjectEntry] = []
    current: ProjectEntry | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_bullet = bool(BULLET_RE.match(stripped))
        is_tech = bool(TECH_LINE_RE.match(stripped))

        if is_bullet or is_tech:
            if current:
                current.text += "\n" + stripped
                if is_bullet:
                    current.has_description_bullet = True
            continue

        if current and current.has_description_bullet and _is_wrapped_line(stripped):
            current.text += "\n" + stripped
            continue

        if current and not current.has_description_bullet:
            current.text += "\n" + stripped
            current.title_line = current.text.split("\n")[0]
            continue

        if current and current.has_description_bullet and _is_likely_new_project_header(stripped):
            entries.append(current)
            current = ProjectEntry(title_line=stripped, text=stripped)
            continue

        if _is_likely_new_project_header(stripped) or current is None:
            if current:
                entries.append(current)
            current = ProjectEntry(title_line=stripped, text=stripped)
        elif current:
            current.text += "\n" + stripped
            current.title_line = current.text.split("\n")[0]

    if current:
        entries.append(current)

    section_end = section.spans[-1].y1 if section.spans else section.y0 + 500
    chunk_height = max((section_end - section.y0) / max(len(entries), 1), 80)

    for i, entry in enumerate(entries):
        y_start = section.y0 + i * chunk_height
        y_end = y_start + chunk_height + 40
        entry.links = [
            link.uri
            for link in doc_links
            if link.page == 1 and y_start <= link.y0 < y_end
        ]

    return entries


def _parse_experience_entries(section: Section) -> list[ExperienceEntry]:
    lines = section.text.splitlines()
    entries: list[ExperienceEntry] = []
    current: ExperienceEntry | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_bullet = bool(BULLET_RE.match(stripped))
        lower = stripped.lower()

        if is_bullet:
            if current:
                current.text += "\n" + stripped
                current.has_description_bullet = True
            continue

        if lower in LOCATION_WORDS:
            if current:
                current.text += "\n" + stripped
            continue

        if current and current.has_description_bullet and _is_wrapped_line(stripped):
            current.text += "\n" + stripped
            continue

        if current and not current.has_description_bullet:
            current.text += "\n" + stripped
            current.title_line = current.text.split("\n")[0]
            continue

        if current and current.has_description_bullet and _is_likely_new_experience_header(stripped):
            entries.append(current)
            current = ExperienceEntry(title_line=stripped, text=stripped)
            continue

        if _is_likely_new_experience_header(stripped) or current is None:
            if current:
                entries.append(current)
            current = ExperienceEntry(title_line=stripped, text=stripped)
        elif current:
            current.text += "\n" + stripped
            current.title_line = current.text.split("\n")[0]

    if current:
        entries.append(current)
    return entries


def derive_metadata(doc: DocumentModel) -> dict[str, str]:
    """Extract roll, name, and college email from PDF for metadata auto-fill."""
    name = doc.header_name
    roll_match = ROLL_NUMBER_PATTERN.search(doc.full_text)
    roll = roll_match.group(0).lower() if roll_match else ""

    college_email = ""
    for link in doc.links:
        if link.uri.lower().startswith("mailto:"):
            addr = link.uri[7:].split("?")[0].split("&")[0]
            if "@sst.scaler.com" in addr.lower():
                college_email = addr
                break

    if not college_email:
        from app.config import COLLEGE_EMAIL_PATTERN

        m = COLLEGE_EMAIL_PATTERN.search(doc.full_text)
        if m:
            college_email = m.group(0)

    return {
        "Name": name,
        "Roll Number": roll,
        "Email": college_email,
    }


def extract_pdf(path: Path) -> DocumentModel:
    path = Path(path)
    doc = fitz.open(path)
    spans: list[TextSpan] = []
    links: list[LinkAnnotation] = []
    image_count = 0

    for pno in range(len(doc)):
        page = doc[pno]
        page_num = pno + 1
        spans.extend(_extract_spans(page, page_num))
        links.extend(_extract_links(page, page_num))
        image_count += len(page.get_images())

    full_text = "\n".join(s.text for s in spans)
    page1 = [s for s in spans if s.page == 1]
    modal_size = _compute_modal_font([s.size for s in spans])
    section_header_info = _find_section_headers(page1, modal_size)
    header_name, header_spans, header_cutoff = _detect_header(page1, modal_size, section_header_info)
    sections = _split_sections(page1, modal_size, section_header_info)

    model = DocumentModel(
        path=path,
        filename=path.name,
        file_size=path.stat().st_size,
        page_count=len(doc),
        spans=spans,
        links=links,
        image_count=image_count,
        full_text=full_text,
        modal_body_font_size=modal_size,
        header_name=header_name,
        header_spans=header_spans,
        sections=sections,
    )
    model.header_cutoff_y = header_cutoff

    projects_section = model.section_by_key("projects")
    if projects_section:
        model.projects = _parse_project_entries(projects_section, links)

    experience_section = model.section_by_key("experience")
    if experience_section:
        model.experiences = _parse_experience_entries(experience_section)

    model.metadata_derived = derive_metadata(model)
    doc.close()
    return model
