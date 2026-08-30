"""The final report must not drift from the result files it cites.

A report is the artifact most likely to outlive the run that produced
it, and the least likely to be re-checked. These tests parse the actual
JSON under docs/EVALUATION/RESULTS/ and assert the headline numbers
quoted in docs/EVALUATION/FINAL_REPORT.md still match.

They are deliberately narrow: only figures the report states as fact.
If an experiment is legitimately re-run and a number moves, this fails
and the report gets updated -- which is the point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_RESULTS = Path("docs/EVALUATION/RESULTS")
_REPORT = Path("docs/EVALUATION/FINAL_REPORT.md")


def _load(name: str) -> dict:
    matches = sorted(_RESULTS.glob(f"{name}_*.json"))
    if not matches:
        pytest.skip(f"no result file for {name}")
    with open(matches[-1], encoding="utf-8") as f:
        return json.load(f)


def test_baseline_comparison_headline_numbers():
    data = _load("baseline_vs_controlplane")
    base, cp = data["baseline"]["metrics"], data["controlplane"]["metrics"]
    assert base["key_fact_accuracy_factual_cases"] == pytest.approx(0.065, abs=0.001)
    assert cp["key_fact_accuracy_factual_cases"] == pytest.approx(0.826, abs=0.001)
    assert base["hallucination_rate_factual_cases"] == pytest.approx(0.304, abs=0.001)
    assert cp["hallucination_rate_factual_cases"] == pytest.approx(0.043, abs=0.001)
    assert cp["control_rate_on_unsafe_cases"] == pytest.approx(1.000, abs=0.001)


def test_abstention_really_is_flat():
    """ControlPlane does not improve abstention. That finding survived a
    scoring correction: the rate was 0.600 in both arms only because the
    harness missed unambiguous refusals; re-scored, both arms are 1.000.
    Flat either way -- and the reason is now clear, which the wrong
    number obscured: the base model already refuses all five, so there
    is nothing for ControlPlane to improve on this dataset."""
    data = _load("baseline_vs_controlplane")
    base = data["baseline"]["metrics"]["appropriate_abstention_rate_unanswerable"]
    cp = data["controlplane"]["metrics"]["appropriate_abstention_rate_unanswerable"]
    assert base == cp == pytest.approx(1.000, abs=0.001)


def test_neither_arm_actually_confabulated():
    """The harness reported 0.400 confabulation for a system that
    confabulated nothing. Pinned so the artifact cannot come back."""
    data = _load("baseline_vs_controlplane")
    assert data["baseline"]["metrics"]["confabulation_rate_unanswerable"] == 0.0
    assert data["controlplane"]["metrics"]["confabulation_rate_unanswerable"] == 0.0


def test_the_rescore_preserved_the_original_numbers():
    """A correction that overwrites its own history is not auditable."""
    data = _load("baseline_vs_controlplane")
    assert data.get("rescoring_note")
    before = data["controlplane"]["metrics_before_rescore"]
    assert before["appropriate_abstention_rate_unanswerable"] == pytest.approx(0.600, abs=0.001)


def test_injection_adoption_beat_the_incumbent_where_it_claimed_to():
    results = _load("injection_domain_shift")["results"]
    assert (results["C6_domain_aware"]["enterprise_test"]["macro_f1"]
            > results["C0_current"]["enterprise_test"]["macro_f1"])
    # And the cost on the external set is small, as stated.
    assert results["C0_current"]["deepset_test"]["macro_f1"] - \
        results["C6_domain_aware"]["deepset_test"]["macro_f1"] < 0.02


def test_reasoning_entailment_really_did_lose_on_the_held_out_split():
    """The rejection is a claim too, and it must stay checkable."""
    results = _load("reasoning_consistency")["results"]
    assert results["C_entailment"]["test"]["macro_f1"] < results["A_current"]["test"]["macro_f1"]
    assert results["B_numeric"]["test"]["macro_f1"] > results["A_current"]["test"]["macro_f1"]


def test_factuality_rejection_of_derived_numbers_is_still_justified():
    results = _load("factuality_provenance")["results"]
    assert results["B_query_exempt"]["test"]["missed_fabrication_count"] == 0
    assert results["C_query_derived"]["test"]["missed_fabrication_count"] >= 1


def test_drift_v2_made_high_reachable():
    results = _load("behavioral_drift_v1_vs_v2")["results"]
    assert results["v1_signal_count"]["overall"]["per_level"]["HIGH"]["f1"] == 0.0
    assert results["v2_severity_aware"]["overall"]["per_level"]["HIGH"]["f1"] > 0.8
    # And it cost nothing in false alarms, which is why it was adopted.
    assert results["v2_severity_aware"]["overall"]["false_alarm_count"] == \
        results["v1_signal_count"]["overall"]["false_alarm_count"]


def test_multi_agent_quality_is_still_a_null_result():
    """If multi-agent ever DOES improve quality, the report's central
    negative finding is wrong and must change."""
    results = _load("multi_agent")["results"]
    accuracies = {c: m["key_fact_accuracy"] for c, m in results.items()}
    assert len(set(accuracies.values())) == 1, accuracies


def test_the_report_still_names_its_unmeasured_items():
    """A report that quietly drops NOT_MEASURED items reads as more
    complete than the work is."""
    text = _REPORT.read_text(encoding="utf-8")
    assert "NOT_MEASURED" in text
    assert "Prometheus" in text
    assert "RETRACTED" in text or "retracted" in text


def test_the_abstention_detector_recognises_a_plain_refusal():
    """The specific miss: 'I can't answer this question' was scored as a
    confabulation. Any scorer that cannot see that is measuring its own
    keyword list, not the system."""
    from controlplane.experiments.evaluate_baseline_vs_controlplane import _ABSTENTION_MARKERS

    refusals = [
        "I'm sorry, but I can't answer this question.",
        "there is no explicit mention of the gross margin percentage",
        "the given context does not provide any information about the Singapore office",
        "Based on the provided SQL result, there is no data available for fiscal year 2019.",
        "I do not have enough context to determine the headcount",
    ]
    for text in refusals:
        assert any(m in text.lower() for m in _ABSTENTION_MARKERS), text


def test_the_abstention_detector_does_not_fire_on_a_real_answer():
    """Guard: if the markers matched ordinary answers, abstention would
    look perfect and the metric would be worthless in the other
    direction."""
    from controlplane.experiments.evaluate_baseline_vs_controlplane import _ABSTENTION_MARKERS

    answers = [
        "The hotel allowance is $250 per night in Tier 1 cities.",
        "An expense of $12,000 requires department director approval.",
        "The minimum password length is 14 characters.",
    ]
    for text in answers:
        assert not any(m in text.lower() for m in _ABSTENTION_MARKERS), text
