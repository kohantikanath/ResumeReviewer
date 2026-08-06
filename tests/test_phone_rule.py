"""R302 — phone present (plain text or tel link, both portals)."""

from pathlib import Path

from app.models import DocumentModel, LinkAnnotation, TextSpan
from app.rules.header_rules import check_header_rules


def _doc(header: str, full_text: str | None = None, links: list[LinkAnnotation] | None = None):
    text = full_text or header
    doc = DocumentModel(
        path=Path("resume.pdf"),
        filename="resume.pdf",
        file_size=1000,
        page_count=1,
        full_text=text,
        header_name="Test User",
        header_spans=[
            TextSpan(text=header, size=14, x0=0, y0=10, x1=200, y1=20, page=1),
        ],
        links=links or [],
    )
    return doc


def _r302(doc: DocumentModel):
    return next(r for r in check_header_rules(doc) if r.rule_id == "R302")


def test_r302_plain_digits():
    assert _r302(_doc("Navneet | 9876543210")).passed


def test_r302_spaced_digits():
    assert _r302(_doc("Navneet | +91 98765 43210")).passed


def test_r302_hyphenated_digits():
    assert _r302(_doc("Navneet | +91-98765-43210")).passed


def test_r302_tel_link_without_visible_text():
    doc = _doc(
        "Navneet Kumar",
        links=[
            LinkAnnotation(
                uri="tel:+919876543210",
                page=1,
                x0=0,
                y0=10,
                x1=50,
                y1=20,
                kind=2,
            ),
        ],
    )
    assert _r302(doc).passed


def test_r302_plain_text_no_link_required():
    doc = _doc("Phone: 8765432109 | no link here")
    assert _r302(doc).passed


def test_r302_missing_phone():
    assert not _r302(_doc("Navneet Kumar | navneet@sst.scaler.com")).passed
