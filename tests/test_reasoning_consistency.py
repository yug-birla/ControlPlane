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


# --- the numeric layer is actually wired into the live evaluator ----
#
# The whole point of §30 is that the EVALUATOR improves, not that a
# module exists. These assert on ReasoningEvaluator, the thing the
# runtime evaluation suite actually calls.


def test_the_live_evaluator_catches_a_numeric_self_contradiction():
    from controlplane.evaluation.evaluators import EvaluationContext, ReasoningEvaluator

    result = ReasoningEvaluator().evaluate(EvaluationContext(
        query="How long is the notice period for managers?",
        answer="Managers must give 60 days notice. The required notice for managers is 30 days.",
    ))
    assert result.label == "SELF_CONTRADICTORY"


def test_the_live_evaluator_still_catches_the_polarity_case():
    """Guard: adding a layer must not lose the one the evaluator already
    handled."""
    from controlplane.evaluation.evaluators import EvaluationContext, ReasoningEvaluator

    result = ReasoningEvaluator().evaluate(EvaluationContext(
        query="Is remote work allowed for new hires?",
        answer="Remote work is allowed for new hires, but remote work is not allowed for new hires.",
    ))
    assert result.label == "SELF_CONTRADICTORY"


def test_the_live_evaluator_does_not_flag_an_ordinary_comparison():
    from controlplane.evaluation.evaluators import EvaluationContext, ReasoningEvaluator

    result = ReasoningEvaluator().evaluate(EvaluationContext(
        query="What notice period applies to a six-month contract?",
        answer="A six-month contract requires 30 days notice, which is half the 60 days required for annual contracts.",
    ))
    assert result.label == "NO_CONTRADICTION_DETECTED"


def test_the_live_evaluator_does_not_load_a_model():
    """The entailment layer was measured and rejected partly on latency:
    60-545ms per call inside a live per-request suite. If it is ever
    wired in by accident, this fails."""
    import sys

    from controlplane.evaluation.evaluators import EvaluationContext, ReasoningEvaluator

    before = "transformers" in sys.modules
    ReasoningEvaluator().evaluate(EvaluationContext(
        query="q", answer="The limit is $500 and the limit is $900 for the same category."))
    if not before:
        assert "transformers" not in sys.modules, "the live reasoning evaluator loaded a model"


# --- hard unanswerable dataset integrity (§27) -------------------
#
# Created after measuring that the existing 5 UNANSWERABLE cases cannot
# discriminate between baseline and ControlPlane: the base model already
# refuses all five, because every one is a topic that is entirely absent
# from the corpus. These cases put ADJACENT evidence in reach instead.


def _hard_unanswerable():
    import json
    from pathlib import Path

    return json.loads(Path("data/raw/generated/hard_unanswerable_cases.json").read_text(encoding="utf-8-sig"))


def test_every_hardness_type_has_an_answerable_control():
    """A system that refuses everything scores perfectly on abstention.
    Controls are what make the metric mean something, and they are
    deliberately one word away from their unanswerable twin."""
    cases = _hard_unanswerable()
    controls = [c for c in cases if c["expected_behaviour"] == "ANSWER"]
    assert len(controls) >= 5
    assert len(controls) / len(cases) >= 0.25


def test_the_hard_cases_are_not_just_absent_topics():
    """The existing 5 are all 'topic entirely missing', which is why the
    base model refuses them without help. These must be harder than
    that: each names the adjacent evidence that makes it tempting."""
    for case in _hard_unanswerable():
        if case["expected_behaviour"] == "ANSWER":
            continue
        assert case.get("tempting_wrong_answer"), case["case_id"]
        assert case.get("why_hard"), case["case_id"]


def test_hard_unanswerable_is_disjoint_from_the_frozen_benchmark():
    """The 62-case set is the primary comparison and must not absorb
    these, or the comparison stops being reproducible (§6)."""
    import json
    from pathlib import Path

    frozen = {c["query"] for c in json.loads(
        Path("data/raw/generated/baseline_vs_controlplane_cases.json").read_text(encoding="utf-8-sig"))}
    assert not frozen & {c["query"] for c in _hard_unanswerable()}


def test_hard_unanswerable_has_a_held_out_split():
    from collections import Counter

    splits = Counter(c["split"] for c in _hard_unanswerable())
    assert set(splits) == {"dev", "test"}
    # Stratified: both splits must contain must-abstain AND controls.
    for split in ("dev", "test"):
        behaviours = {c["expected_behaviour"] for c in _hard_unanswerable() if c["split"] == split}
        assert "ANSWER" in behaviours and "ABSTAIN_OR_QUALIFY" in behaviours
