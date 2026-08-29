"""Regression tests for numeric self-contradiction detection.

The false-positive guards below matter more than the positive cases. A
contradiction detector that fires on correctly-scoped answers would sit
in the live evaluation suite and drive exactly the over-control that
Milestone 15 spent a benchmark reducing -- so each guard pins a specific
way this check could start over-firing.

No model is loaded here: these cover the deterministic numeric layer
only. The entailment layer is measured in
``controlplane/experiments/evaluate_reasoning_consistency.py`` rather
than unit-tested, because asserting on a generative model's zero-shot
output in a per-commit test would pin a number that is not a property of
this code.
"""

from __future__ import annotations

from controlplane.evaluation.reasoning_consistency import (
    check_numeric_consistency,
    extract_numeric_claims,
    split_clauses,
)


# --- clause splitting -------------------------------------------

def test_contrastive_conjunctions_split_a_single_sentence():
    """The split-polarity failures put both halves of a contradiction in
    ONE sentence joined by "and"/"though". Sentence splitting alone
    leaves them invisible, which is why the keyword evaluator missed
    them."""
    clauses = split_clauses(
        "Contractors must complete the security module, though contractors are not required to complete it."
    )
    assert len(clauses) == 2


def test_short_fragments_are_dropped():
    assert all(len(c.split()) >= 3 for c in split_clauses("Yes. It is 40 hours across five days."))


# --- numeric claim extraction -----------------------------------

def test_currency_is_parsed_with_thousands_separators_and_suffixes():
    values = {c.value for c in extract_numeric_claims("Limits are $10,000 and $2.5k and $1m today")}
    assert {10000.0, 2500.0, 1000000.0} <= values


def test_units_are_normalised_so_unlike_quantities_never_compare():
    units = {c.unit for c in extract_numeric_claims("It takes 30 days or 30 hours or 30 percent")}
    assert units == {"day", "hour", "percent"}


# --- positive detection -----------------------------------------

def test_same_subject_conflicting_values_is_flagged():
    findings = check_numeric_consistency(
        "Managers must give 60 days notice. The required notice for managers is 30 days."
    )
    assert findings and findings[0].kind == "NUMERIC"


def test_a_silently_widened_limit_is_flagged():
    findings = check_numeric_consistency(
        "A manager may approve purchases up to $10,000 without escalation, "
        "so any purchase under $25,000 can be manager-approved."
    )
    assert findings


# --- false-positive guards --------------------------------------

def test_different_subjects_with_different_numbers_are_not_flagged():
    """Guard: an ordinary comparison. Two different values for two
    different subjects is the single most common shape a naive
    "two numbers disagree" rule gets wrong."""
    assert not check_numeric_consistency(
        "A six-month contract requires 30 days notice, which is half the 60 days required for annual contracts."
    )


def test_identical_boundary_numbers_are_not_flagged():
    """Guard: threshold answers legitimately repeat the same figure."""
    assert not check_numeric_consistency(
        "A payment of exactly $10,000 is within the manager limit of $10,000 and does not need director approval."
    )


def test_numbers_in_different_roles_are_not_flagged():
    """Guard: a correct multi-step answer carries several numbers that
    play different roles (a count, a threshold, an amount)."""
    assert not check_numeric_consistency(
        "A $30,000 purchase needs 2 approvals: it exceeds the $10,000 manager limit, "
        "so it also requires a director signature."
    )


def test_unlike_units_never_conflict():
    """Guard: 15 minutes and 1 hour are not a disagreement, and would be
    one if units were ignored."""
    assert not check_numeric_consistency(
        "The gateway RTO is 15 minutes. The database RPO is 1 hour."
    )


def test_a_wrong_but_internally_consistent_answer_is_not_flagged():
    """Guard, and a scope statement: this checks for CONTRADICTION, not
    for CORRECTNESS. 5 x 2 x $120 is $1,200, so $600 is wrong -- but
    nothing in the answer contradicts anything else in it, and claiming
    otherwise would misreport what this evaluator can know."""
    assert not check_numeric_consistency("The total is $600.")


# --- multi-source / conflict dataset integrity ------------------
#
# A benchmark case whose "expected value" appears nowhere in the corpus
# is unscoreable: it can never be answered correctly, and it would show
# up as a permanent model failure rather than as a broken case. This
# guards the dataset itself.


def test_multi_source_expected_values_are_present_in_the_corpus_or_derived():
    import csv  # noqa: F401  (kept for symmetry with the data layout)
    import json
    from pathlib import Path

    cases = json.loads(Path("data/raw/generated/multi_source_conflict_cases.json").read_text(encoding="utf-8-sig"))
    corpus = " ".join(p.read_text(encoding="utf-8", errors="ignore")
                      for p in Path("data/synthetic_enterprise/documents").glob("*.txt"))
    database = " ".join(p.read_text(encoding="utf-8-sig", errors="ignore")
                        for p in Path("data/synthetic_enterprise/database").glob("*.csv"))
    haystack = (corpus + " " + database).replace(",", "")

    unscoreable = []
    for case in cases:
        derived = set(case.get("derived_expected_values") or [])
        for value in case.get("expected_values") or []:
            if value in derived:
                continue  # computed, deliberately not quotable from source
            if value.replace(",", "") not in haystack:
                unscoreable.append((case["case_id"], value))
    assert not unscoreable, f"expected values absent from corpus and DB: {unscoreable}"


def test_conflict_cases_include_a_false_positive_guard():
    """Without a case where sources merely LOOK inconsistent, a system
    that reports a conflict on every cross-document difference scores
    perfectly on conflict detection and is useless."""
    import json
    from pathlib import Path

    cases = json.loads(Path("data/raw/generated/multi_source_conflict_cases.json").read_text(encoding="utf-8-sig"))
    assert any(c.get("expected_conflict") is False for c in cases)
    assert any(c.get("expected_conflict") is True for c in cases)


def test_some_cases_require_abstention_rather_than_an_answer():
    """Multi-source questions where the sources are jointly insufficient
    must be represented, or the dataset only rewards answering."""
    import json
    from pathlib import Path

    cases = json.loads(Path("data/raw/generated/multi_source_conflict_cases.json").read_text(encoding="utf-8-sig"))
    assert sum(1 for c in cases if c.get("expected_abstention")) >= 2
