"""Tests for R104 name matching rules."""

from app.rules.name_match import NameMatchOutcome, evaluate_name_match


def test_full_name_pass():
    r = evaluate_name_match("Kohantika Nath", "Kohantika Nath")
    assert r.outcome == NameMatchOutcome.PASS


def test_first_name_only_pass():
    r = evaluate_name_match("Kohantika Nath", "Kohantika")
    assert r.outcome == NameMatchOutcome.PASS


def test_concatenated_pass():
    r = evaluate_name_match("Kohantika Nath", "Kohantikanath")
    assert r.outcome == NameMatchOutcome.PASS


def test_case_insensitive_pass():
    r = evaluate_name_match("Kohantika Nath", "kohantika")
    assert r.outcome == NameMatchOutcome.PASS


def test_truncation_hard_fail():
    r = evaluate_name_match("Kohantika Nath", "kohan")
    assert r.outcome == NameMatchOutcome.HARD_FAIL
    assert "truncation" in r.reason.lower() or "incomplete" in r.reason.lower()


def test_partial_junk_hard_fail():
    r = evaluate_name_match("Kohantika Nath", "kohantikaN")
    assert r.outcome == NameMatchOutcome.HARD_FAIL


def test_surname_only_soft_fail():
    r = evaluate_name_match("Kohantika Nath", "Nath")
    assert r.outcome == NameMatchOutcome.SOFT_FAIL
    assert "surname" in r.reason.lower()
