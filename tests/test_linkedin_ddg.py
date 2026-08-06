"""Tests for DuckDuckGo profile verification (mocked)."""

from unittest.mock import MagicMock, patch

from app.links.linkedin_ddg import (
    apply_ddg_result_to_status,
    extract_linkedin_vanity,
    ProfileDDGResult,
    verify_linkedin_via_ddg,
    verify_profile_via_ddg,
)
from app.links.validator import check_urls


def test_extract_vanity():
    assert extract_linkedin_vanity("https://www.linkedin.com/in/satyanadella/") == "satyanadella"


@patch("app.links.linkedin_ddg.DDGS")
def test_verify_valid(mock_ddgs_class):
    mock_ddgs = MagicMock()
    mock_ddgs_class.return_value = mock_ddgs
    mock_ddgs.text.return_value = [
        {
            "title": "Satya Nadella | LinkedIn",
            "href": "https://www.linkedin.com/in/satyanadella",
            "body": "",
        }
    ]
    result = verify_profile_via_ddg("https://linkedin.com/in/satyanadella")
    assert result.status == "VALID"


@patch("app.links.linkedin_ddg.DDGS")
def test_verify_broken(mock_ddgs_class):
    mock_ddgs = MagicMock()
    mock_ddgs_class.return_value = mock_ddgs
    mock_ddgs.text.return_value = []
    result = verify_profile_via_ddg("https://linkedin.com/in/notrealuserxyz123")
    assert result.status == "BROKEN_OR_PRIVATE"


def test_apply_ddg_result():
    ok = ProfileDDGResult("VALID", "ok")
    assert apply_ddg_result_to_status(ok, (999, "ok")) == (200, "ddg:valid")
    broken = ProfileDDGResult("BROKEN_OR_PRIVATE", "missing")
    assert apply_ddg_result_to_status(broken, (403, "ok")) == (
        403,
        "profile_bot_block_unverified",
    )
    assert apply_ddg_result_to_status(broken, (404, "ok")) == (404, "ddg_not_indexed")


@patch("app.links.validator.verify_profile_via_ddg_async")
async def test_check_urls_ddg_fallback(mock_verify):
    mock_verify.return_value = ProfileDDGResult("VALID", "ok")
    url = "https://www.linkedin.com/in/testuser"
    cache = {url: (404, "ok")}
    await check_urls([url], cache=cache, use_ddg_linkedin=True)
    assert cache[url] == (200, "ddg:valid")
    mock_verify.assert_called_once()


@patch("app.links.validator.verify_profile_via_ddg_async")
async def test_check_urls_skips_ddg_for_bot_block(mock_verify):
    url = "https://www.linkedin.com/in/testuser"
    cache = {url: (999, "ok")}
    await check_urls([url], cache=cache, use_ddg_linkedin=True)
    mock_verify.assert_not_called()
    assert cache[url] == (403, "profile_bot_block_unverified")


def test_cli_helper_ignores_name():
    with patch("app.links.linkedin_ddg._profile_indexed", return_value=True):
        result = verify_linkedin_via_ddg("https://linkedin.com/in/foo", "Wrong Name")
        assert result.status == "VALID"
