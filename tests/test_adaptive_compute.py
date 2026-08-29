"""Adaptive compute allocation.

The property under test: spend more compute only when it is justified,
and choose escalation only when observed history supports it.
"""

from __future__ import annotations

from controlplane.routing.adaptive_compute import (
    AdaptiveComputePolicy,
    ComputeAction,
    build_refinement_prompt,
)
from controlplane.routing.model_performance import (
    ModelProfile,
    escalation_is_evidence_backed,
)


def _policy() -> AdaptiveComputePolicy:
    return AdaptiveComputePolicy()


def test_no_quality_concern_spends_nothing_more():
    d = _policy().decide(
        quality_concerns=[], current_role="FAST", refinement_passes_used=0,
        risk_severity="LOW_RISK", escalation_supported=False,
    )
    assert d.action is ComputeAction.STOP


def test_safety_flags_are_not_treated_as_compute_problems():
    """A detected injection or high-risk action is a hard constraint
    handled by the Decision Engine, not something more tokens can fix.
    Treating it as a quality concern would spend compute AND muddy the
    governance path."""
    d = _policy().decide(
        quality_concerns=["prompt_injection", "action_risk", "safety"],
        current_role="FAST", refinement_passes_used=0,
        risk_severity="HIGH_RISK", escalation_supported=True,
    )
    assert d.action is ComputeAction.STOP
    assert d.triggering_evaluators == []


def test_quality_concern_without_escalation_evidence_prefers_cheap_refinement():
    """THE central behaviour. Escalation costs ~2.5x per token on this
    project and measured WORSE quality, so an unevidenced escalation
    reliably spends more to get less."""
    d = _policy().decide(
        quality_concerns=["grounding"], current_role="FAST", refinement_passes_used=0,
        risk_severity="LOW_RISK", escalation_supported=False,
        escalation_reason="observed grounding rate is not better",
    )
    assert d.action is ComputeAction.SELF_REFINE
    assert d.target_model_role == "FAST"
    assert "not evidence-backed" in d.reason.lower()


def test_quality_concern_with_escalation_evidence_escalates():
    """The same policy escalates when the evidence changes -- the belief
    about which model is better lives in the data, not in the code."""
    d = _policy().decide(
        quality_concerns=["grounding"], current_role="FAST", refinement_passes_used=0,
        risk_severity="LOW_RISK", escalation_supported=True,
        escalation_reason="observed grounding rate 0.81 > 0.62",
    )
    assert d.action is ComputeAction.ESCALATE
    assert d.target_model_role == "STRONG"


def test_strong_path_does_not_self_refine_unnecessarily():
    """The directive is explicit: do not automatically refine on a
    sufficiently capable model. There is also nothing above it to
    escalate to."""
    d = _policy().decide(
        quality_concerns=["grounding"], current_role="STRONG", refinement_passes_used=0,
        risk_severity="LOW_RISK", escalation_supported=False,
    )
    assert d.action is ComputeAction.STOP
    assert "strongest configured path" in d.reason


def test_refinement_is_bounded():
    d = _policy().decide(
        quality_concerns=["grounding"], current_role="FAST", refinement_passes_used=1,
        risk_severity="LOW_RISK", escalation_supported=False,
    )
    assert d.action is ComputeAction.STOP
    assert "budget exhausted" in d.reason


def test_exhausted_attempt_budget_stops_rather_than_looping():
    d = _policy().decide(
        quality_concerns=["grounding"], current_role="FAST", refinement_passes_used=0,
        risk_severity="LOW_RISK", escalation_supported=True, budget_exhausted=True,
    )
    assert d.action is ComputeAction.STOP


# --- escalation evidence gate ---

def _profile(model, n, grounded_rate, scored=None):
    return ModelProfile(
        model=model, sample_count=n, grounded_rate=grounded_rate,
        grounding_scored_count=scored if scored is not None else n,
        failure_rate=0.0, mean_latency_ms=1000.0, mean_output_tokens=50.0,
    )


def test_escalation_needs_observed_evidence_not_model_size():
    profiles = {
        "Qwen/Qwen2.5-1.5B-Instruct": _profile("Qwen/Qwen2.5-1.5B-Instruct", 50, 0.80),
        "Qwen/Qwen3-4B": _profile("Qwen/Qwen3-4B", 50, 0.60),
    }
    ok, reason = escalation_is_evidence_backed(
        profiles, from_model="Qwen/Qwen2.5-1.5B-Instruct", to_model="Qwen/Qwen3-4B"
    )
    assert not ok
    assert "not better" in reason


def test_escalation_is_backed_when_the_bigger_model_actually_wins():
    profiles = {
        "Qwen/Qwen2.5-1.5B-Instruct": _profile("Qwen/Qwen2.5-1.5B-Instruct", 50, 0.60),
        "Qwen/Qwen3-4B": _profile("Qwen/Qwen3-4B", 50, 0.85),
    }
    ok, _ = escalation_is_evidence_backed(
        profiles, from_model="Qwen/Qwen2.5-1.5B-Instruct", to_model="Qwen/Qwen3-4B"
    )
    assert ok


def test_sparse_history_is_not_treated_as_evidence():
    """n=3 is noise. Acting on it would be worse than the static default."""
    profiles = {
        "Qwen/Qwen2.5-1.5B-Instruct": _profile("Qwen/Qwen2.5-1.5B-Instruct", 3, 0.33),
        "Qwen/Qwen3-4B": _profile("Qwen/Qwen3-4B", 3, 1.00),
    }
    ok, reason = escalation_is_evidence_backed(
        profiles, from_model="Qwen/Qwen2.5-1.5B-Instruct", to_model="Qwen/Qwen3-4B"
    )
    assert not ok
    assert "insufficient samples" in reason


def test_missing_history_is_not_treated_as_evidence():
    ok, reason = escalation_is_evidence_backed({}, from_model="a", to_model="b")
    assert not ok
    assert "no observed history" in reason


def test_refinement_prompt_uses_the_evaluator_finding_and_asks_for_no_reasoning():
    """Feedback comes from the independent evaluator, not the model's own
    self-critique -- a small model asked to critique itself tends to agree
    with itself. And no chain-of-thought is requested or stored."""
    prompt = build_refinement_prompt(
        original_prompt="Context: meals are $75/day.\n\nWhat is the meal limit?",
        previous_answer="The company mascot is a penguin.",
        concerns=["grounding", "factuality"],
    )
    assert "grounding, factuality" in prompt
    assert "The company mascot is a penguin." in prompt
    assert "Give only the corrected answer." in prompt
    lowered = prompt.lower()
    assert "step by step" not in lowered and "reasoning" not in lowered
