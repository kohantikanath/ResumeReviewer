"""LeetCode profile URL handling."""

from pathlib import Path
from unittest.mock import patch

from app.links.linkedin_ddg import (
    _href_matches,
    _parse_profile_target,
    apply_ddg_result_to_status,
    ProfileDDGResult,
    verify_profile_via_ddg,
)
from app.rules.link_rules import network_link_results
from app.models import DocumentModel, LinkAnnotation


def test_parse_leetcode_u_path():
    url = "https://leetcode.com/u/akshat-code21/"
    assert _parse_profile_target(url) == ("leetcode", "akshat-code21")


def test_href_matches_leetcode_exact():
    assert _href_matches(
        "leetcode",
        "akshat-code21",
        "https://leetcode.com/u/akshat-code21/",
    )


@patch("app.links.linkedin_ddg._profile_indexed", return_value=False)
def test_leetcode_403_not_hard_fail_when_ddg_misses(mock_indexed):
    """403 + no search hit = soft unverifiable, not broken."""
    result = verify_profile_via_ddg("https://leetcode.com/u/akshat-code21/")
    assert result.status == "BROKEN_OR_PRIVATE"
    entry = apply_ddg_result_to_status(result, (403, "ok"))
    assert entry == (403, "profile_bot_block_unverified")

    doc = DocumentModel(
        path=Path("test.pdf"),
        filename="test.pdf",
        file_size=1,
        page_count=1,
        full_text="",
        links=[
            LinkAnnotation(
                uri="https://leetcode.com/u/akshat-code21/",
                page=1,
                x0=0,
                y0=0,
                x1=1,
                y1=1,
                kind=2,
            )
        ],
    )
    rules = network_link_results(
        doc,
        {"https://leetcode.com/u/akshat-code21/": entry},
    )
    r503 = [r for r in rules if r.rule_id == "R503" and not r.passed]
    r502 = [r for r in rules if r.rule_id == "R502" and not r.passed]
    assert len(r503) == 0
    assert len(r502) == 0


def test_placeholder_url_skips_r502():
    """Placeholder URLs are R501 only — do not also report R502."""
    placeholder = "https://REPLACE-WITH-CLEARPATH-LIVE-URL"
    doc = DocumentModel(
        path=Path("test.pdf"),
        filename="test.pdf",
        file_size=1,
        page_count=1,
        full_text="",
        links=[
            LinkAnnotation(
                uri=placeholder,
                page=1,
                x0=0,
                y0=50,
                x1=1,
                y1=51,
                kind=2,
            ),
        ],
    )
    rules = network_link_results(
        doc,
        {placeholder: (0, "connection_refused")},
    )
    r502_failed = [r for r in rules if r.rule_id == "R502" and not r.passed]
    assert r502_failed == []
