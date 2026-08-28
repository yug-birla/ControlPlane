"""Tests for the baseline-vs-ControlPlane scoring harness.

The scorer decides this project's headline product claim, so a bug in it
is as serious as a bug in the system under test -- and there WAS one
(see test_numeric_needles_match_on_token_boundaries_regression).
"""

from __future__ import annotations

from controlplane.experiments.evaluate_baseline_vs_controlplane import (
    _contains_any,
    _mentions,
    _score_answer,
)


def test_numeric_needles_match_on_token_boundaries_regression():
    """Regression: the contradicting value "6" substring-matched inside
    the correct answer "16 weeks paid", so a correct answer was scored
    as a hallucination. Found during Milestone 9 error analysis by
    reading the per-case rows rather than trusting the aggregate."""
    answer = "According to the HR Policy v2.1, primary caregiver parental leave is 16 weeks paid."
    assert _mentions(answer, "16")
    assert not _mentions(answer, "6")
    assert not _mentions(answer, "12")
    assert not _mentions(answer, "2")  # must not match inside "v2.1"


def test_percentage_needles_do_not_match_inside_larger_percentages():
    assert not _mentions("a service credit of 15% applies", "5%")
    assert _mentions("a service credit of 5% applies", "5%")


def test_currency_and_comma_formatted_numbers_match():
    assert _mentions("dual authorization above $50,000", "50,000")
    assert not _mentions("dual authorization above $150,000", "50,000")


def test_word_needles_still_match_as_substrings_on_purpose():
    """Word values must keep substring behaviour so "annual" matches
    "annually" -- the boundary rule is deliberately numeric-only."""
    assert _mentions("penetration tests are conducted annually", "annual")
    assert _mentions("requires department director approval", "director")


def test_correct_answer_with_no_contradicting_value_scores_correct():
    case = {
        "category": "GROUNDED_POLICY",
        "query": "q",
        "expected_values": ["250"],
        "contradicting_values": ["150", "300"],
    }
    scores = _score_answer(case, "The Tier 1 hotel allowance is $250 per night.", [])
    assert scores["key_fact_correct"]
    assert not scores["hallucinated_fact"]


def test_answer_listing_both_right_and_wrong_values_is_not_correct():
    """Hedging across several candidate figures is not a correct answer."""
    case = {
        "category": "GROUNDED_POLICY",
        "query": "q",
        "expected_values": ["250"],
        "contradicting_values": ["300"],
    }
    scores = _score_answer(case, "It is either $250 or $300 per night.", [])
    assert not scores["key_fact_correct"]
    assert scores["hallucinated_fact"]


def test_withheld_answer_is_never_scored_as_correct():
    """Abstention must not be able to game the correctness metric --
    otherwise a system that blocks everything would look accurate."""
    case = {
        "category": "GROUNDED_POLICY",
        "query": "q",
        "expected_values": ["250"],
        "contradicting_values": [],
    }
    scores = _score_answer(case, None, [])
    assert not scores["asserted_an_answer"]
    assert not scores["key_fact_correct"]


def test_unanswerable_case_declining_counts_as_appropriate_abstention():
    case = {"category": "UNANSWERABLE", "query": "q", "expected_values": [], "contradicting_values": []}
    declined = _score_answer(case, "I don't have access to that information.", [])
    assert declined["appropriately_abstained"]
    assert not declined["confabulated_when_unanswerable"]

    confabulated = _score_answer(case, "The Singapore office has exactly 412 employees.", [])
    assert not confabulated["appropriately_abstained"]
    assert confabulated["confabulated_when_unanswerable"]


def test_contains_any_is_empty_safe():
    assert not _contains_any("some answer", [])
    assert not _mentions("some answer", "")


def test_trailing_sentence_period_does_not_break_numeric_matching_regression():
    r"""Second regression in the same matcher, found the same way: a
    lookahead of (?![\w.]) rejected "The allowance is $250." because of
    the full stop, scoring two correct answers as failures."""
    assert _mentions("The hotel allowance per night for Tier 1 cities is $250.", "250")
    assert _mentions("The meal reimbursement limit per day is up to $75.", "75")
    # ...while still rejecting a decimal continuation.
    assert not _mentions("uptime was 6.5 percent below target", "6")
    assert _mentions("uptime guarantee is 99.9% monthly", "99.9")
