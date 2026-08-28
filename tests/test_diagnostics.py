"""Component-level failure localization.

The product question these protect: "WHICH component failed and why?",
not merely "did the request fail?".
"""

from __future__ import annotations

from controlplane.diagnostics.component_state import (
    Attribution,
    Component,
    ComponentStatus,
    localize_failure,
)
from controlplane.diagnostics.report import build_component_reports, localize


def _eval(evaluator, label, signal="OK"):
    return {"evaluator": evaluator, "label": label, "recommended_signal": signal}


def test_no_flags_and_verified_is_no_failure():
    result = localize_failure(
        evaluations=[_eval("grounding", "SUPPORTED")],
        decision={"action": "CONTINUE"},
        verification={"status": "VERIFIED"},
        retrieval_ran=True, evidence_count=3, failed_steps=[],
    )
    assert result.attribution is Attribution.NO_FAILURE


def test_a_step_that_actually_failed_beats_any_inference():
    result = localize_failure(
        evaluations=[_eval("grounding", "UNSUPPORTED", "FLAG_FOR_REVIEW")],
        decision=None, verification=None,
        retrieval_ran=False, evidence_count=0,
        failed_steps=["route:data_rag"],
    )
    assert result.attribution is Attribution.COMPONENT_FAILURE
    assert result.component is Component.RETRIEVAL


def test_ungrounded_answer_with_no_retrieval_is_a_ROUTING_failure_regression():
    """THE case this module exists for, and a regression against the real
    Milestone 9 bug: RAG-hint recall was 0.053, so corpus-answerable
    questions never retrieved and ControlPlane returned the unmanaged
    model's answer verbatim -- while every component reported success.

    Blaming GENERATION here would be wrong and would have hidden that
    bug: the model was never given anything to ground against."""
    result = localize_failure(
        evaluations=[_eval("grounding", "UNSUPPORTED", "FLAG_FOR_REVIEW")],
        decision={"action": "RETRIEVE_MORE"}, verification={"status": "NOT_VERIFIED"},
        retrieval_ran=False, evidence_count=0, failed_steps=[],
    )
    assert result.attribution is Attribution.COMPONENT_FAILURE
    assert result.component is Component.CAPABILITY_ROUTER
    assert "routing failure" in result.reason


def test_ungrounded_answer_despite_evidence_is_a_generation_failure():
    """The complement: evidence WAS retrieved and the model still didn't
    use it. That is genuinely generation's fault."""
    result = localize_failure(
        evaluations=[_eval("grounding", "UNSUPPORTED", "FLAG_FOR_REVIEW")],
        decision=None, verification=None,
        retrieval_ran=True, evidence_count=4, failed_steps=[],
    )
    assert result.component is Component.GENERATION


def test_retrieval_that_returned_nothing_is_a_retrieval_failure():
    result = localize_failure(
        evaluations=[_eval("rag_adequacy", "INSUFFICIENT", "FLAG_FOR_REVIEW")],
        decision=None, verification=None,
        retrieval_ran=True, evidence_count=0, failed_steps=[],
    )
    assert result.component is Component.RETRIEVAL


def test_blocked_prompt_injection_is_governed_input_not_a_component_failure():
    """Correct governance must not be reported as a defect -- otherwise
    the failure dashboard punishes the system for working."""
    result = localize_failure(
        evaluations=[_eval("prompt_injection", "INJECTION_PATTERN_DETECTED", "FLAG_FOR_REVIEW")],
        decision={"action": "HUMAN_REVIEW"}, verification={"status": "REJECTED"},
        retrieval_ran=False, evidence_count=0, failed_steps=[],
    )
    assert result.attribution is Attribution.INPUT_GOVERNED
    assert result.component is None


def test_high_risk_action_is_governed_input_not_a_component_failure():
    result = localize_failure(
        evaluations=[_eval("action_risk", "HIGH_RISK", "FLAG_FOR_REVIEW")],
        decision={"action": "HUMAN_REVIEW"}, verification={"status": "REJECTED"},
        retrieval_ran=False, evidence_count=0, failed_steps=[],
    )
    assert result.attribution is Attribution.INPUT_GOVERNED


def test_input_governance_is_checked_before_quality_evaluators():
    """A blocked injection that also happens to be ungrounded must be
    reported as governed input, not as a routing/generation defect."""
    result = localize_failure(
        evaluations=[
            _eval("grounding", "UNSUPPORTED", "FLAG_FOR_REVIEW"),
            _eval("prompt_injection", "INJECTION_PATTERN_DETECTED", "FLAG_FOR_REVIEW"),
        ],
        decision=None, verification=None,
        retrieval_ran=False, evidence_count=0, failed_steps=[],
    )
    assert result.attribution is Attribution.INPUT_GOVERNED


def test_verification_failing_with_no_flags_is_reported_as_undetermined():
    """Never invent a culprit. Verification and evaluation disagreeing is
    itself the finding."""
    result = localize_failure(
        evaluations=[_eval("grounding", "SUPPORTED")],
        decision={"action": "CONTINUE"}, verification={"status": "REJECTED"},
        retrieval_ran=True, evidence_count=2, failed_steps=[],
    )
    assert result.attribution is Attribution.UNDETERMINED
    assert result.component is Component.VERIFICATION


def test_component_reports_cover_the_pipeline_and_mark_the_triggering_evaluator():
    steps = [
        {"step_type": "query_profiling", "status": "COMPLETED", "started_at": None, "completed_at": None},
        {"step_type": "risk_assessment", "status": "COMPLETED", "started_at": None, "completed_at": None},
        {"step_type": "routing", "status": "COMPLETED", "started_at": None, "completed_at": None},
    ]
    graph_nodes = [
        {"node_id": "data_rag", "capability": "RAG", "status": "COMPLETED", "latency_ms": 40},
        {"node_id": "generation", "capability": "GENERAL", "status": "COMPLETED", "latency_ms": 900},
    ]
    evaluations = [_eval("grounding", "UNSUPPORTED", "FLAG_FOR_REVIEW"), _eval("factuality", "SUPPORTED")]
    reports = build_component_reports(
        steps=steps, graph_nodes=graph_nodes, evaluations=evaluations,
        decision={"action": "RETRIEVE_MORE", "reason": "ungrounded",
                  "triggering_evaluator": "grounding", "attempt_number": 1,
                  "requires_intervention": True},
        verification={"status": "NOT_VERIFIED", "reason": "grounding failed"},
        trust={"level": "LOW", "reason": "verification failed"},
        risk={"severity": "LOW_RISK"},
        fingerprint={"intent": "FACTUAL_LOOKUP", "complexity": "LOW", "capability_hints": ["RAG"]},
        model_meta={"provider": "local_hf_generation", "model": "Qwen", "role": "STRONG", "latency_ms": 900},
    )
    components = [r.component for r in reports]
    for expected in (Component.QUERY_PROFILER, Component.RISK_PROFILER, Component.CAPABILITY_ROUTER,
                      Component.RETRIEVAL, Component.GENERATION, Component.EVALUATION,
                      Component.DECISION, Component.VERIFICATION, Component.TRUST):
        assert expected in components, f"{expected} missing from the component report"

    grounding = next(r for r in reports
                     if r.component is Component.EVALUATION and "grounding" in r.summary)
    assert grounding.status is ComponentStatus.DEGRADED
    assert grounding.decision_impact == "triggered the control decision"


def test_localize_reads_the_persisted_graph_snapshot_shape():
    """`localize` must accept the shape actually stored in
    route_decisions.execution_graph, not a hand-shaped dict."""
    result = localize(
        steps=[{"step_type": "routing", "status": "COMPLETED"}],
        graph_nodes=[{"node_id": "generation", "capability": "GENERAL", "status": "COMPLETED"}],
        evaluations=[_eval("grounding", "UNSUPPORTED", "FLAG_FOR_REVIEW")],
        decision=None, verification=None,
    )
    # No RAG/SQL node ran at all -> routing, per the regression above.
    assert result.component is Component.CAPABILITY_ROUTER


def test_capability_hints_persisted_as_a_values_dict_are_read_correctly_regression():
    """Regression: list-valued profile fields are persisted as
    {"values": [...]}, and iterating the dict yielded its KEYS -- the
    dashboard showed the literal signal "values" instead of "RAG".
    Found by running the diagnostics against real persisted data rather
    than only hand-built fixtures."""
    reports = build_component_reports(
        steps=[{"step_type": "query_profiling", "status": "COMPLETED",
                "started_at": None, "completed_at": None}],
        graph_nodes=[], evaluations=[], decision=None, verification=None, trust=None,
        risk=None,
        fingerprint={"intent": "FACTUAL_LOOKUP", "complexity": "LOW",
                     "capability_hints": {"values": ["RAG", "GENERAL"]}},
        model_meta=None,
    )
    profiler = next(r for r in reports if r.component is Component.QUERY_PROFILER)
    assert profiler.signal == "RAG+GENERAL"


def test_plain_list_capability_hints_still_work():
    reports = build_component_reports(
        steps=[{"step_type": "query_profiling", "status": "COMPLETED",
                "started_at": None, "completed_at": None}],
        graph_nodes=[], evaluations=[], decision=None, verification=None, trust=None,
        risk=None, fingerprint={"capability_hints": ["SQL"]}, model_meta=None,
    )
    assert next(r for r in reports if r.component is Component.QUERY_PROFILER).signal == "SQL"
