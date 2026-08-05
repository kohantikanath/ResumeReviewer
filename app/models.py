"""Structured document model produced from PDF extraction."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TextSpan:
    text: str
    size: float
    x0: float
    y0: float
    x1: float
    y1: float
    page: int


@dataclass
class LinkAnnotation:
    uri: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    kind: int


@dataclass
class Section:
    key: str
    title: str
    spans: list[TextSpan] = field(default_factory=list)
    text: str = ""
    y0: float = 0.0


@dataclass
class ProjectEntry:
    title_line: str
    text: str
    links: list[str] = field(default_factory=list)
    has_description_bullet: bool = False


@dataclass
class ExperienceEntry:
    title_line: str
    text: str
    has_description_bullet: bool = False


@dataclass
class DocumentModel:
    path: Path
    filename: str
    file_size: int
    page_count: int
    spans: list[TextSpan] = field(default_factory=list)
    links: list[LinkAnnotation] = field(default_factory=list)
    image_count: int = 0
    full_text: str = ""
    modal_body_font_size: float = 9.0
    header_name: str = ""
    header_spans: list[TextSpan] = field(default_factory=list)
    header_cutoff_y: float = 200.0
    sections: list[Section] = field(default_factory=list)
    projects: list[ProjectEntry] = field(default_factory=list)
    experiences: list[ExperienceEntry] = field(default_factory=list)
    metadata_derived: dict[str, Any] = field(default_factory=dict)

    def section_by_key(self, key: str) -> Section | None:
        for section in self.sections:
            if section.key == key:
                return section
        return None

    def header_text(self) -> str:
        return "\n".join(s.text for s in self.header_spans)

    def header_links(self) -> list[LinkAnnotation]:
        cutoff = self.header_cutoff_y
        return [
            link for link in self.links
            if link.page == 1 and link.y0 < cutoff
        ]
