from controlplane.decision.engine import ControlAction, DecisionEngine
from controlplane.evaluation.evaluators import EvaluationResult, EvaluationStatus
from controlplane.policy.baseline import PolicyBaseline
from controlplane.risk.profile import ControlDepth, RiskProfile, RiskSeverity
from controlplane.routing.model_router import ModelRouteAction, ModelRouteDecision

_DIMS = {d: RiskSeverity.NO_ACTION for d in
         ("factuality", "reasoning", "privacy", "pii", "security", "bias", "financial", "action", "safety")}


def _risk(severity=RiskSeverity.NO_ACTION) -> RiskProfile:
    return RiskProfile(risk_dimensions=_DIMS, severity=severity, recommended_control_depth=ControlDepth.FAST_PATH)


def _model_decision(role="FAST", require_verification=False) -> ModelRouteDecision:
    return ModelRouteDecision(
        action=ModelRouteAction.USE_FAST_MODEL if role == "FAST" else ModelRouteAction.USE_STRONG_MODEL,
        model_role=role, require_verification=require_verification, human_approval_required=False,
        reason="test", expected_cost_class="LOW", expected_latency_class="LOW",
    )


def _eval(name, label, score=None):
    return EvaluationResult(evaluator=name, status=EvaluationStatus.IMPLEMENTED, label=label, score=score, rationale="test")


def test_no_concerns_continues():
    decision = DecisionEngine().decide([], _risk(), _model_decision(), attempt_number=1)
    assert decision.action == ControlAction.CONTINUE
    assert decision.can_retry is True


def test_unsupported_grounding_triggers_retrieve_more_on_first_attempt():
    results = [_eval("grounding", "UNSUPPORTED", 0.1)]
    decision = DecisionEngine(max_attempts=2).decide(results, _risk(), _model_decision(), attempt_number=1)
    assert decision.action == ControlAction.RETRIEVE_MORE
    assert decision.requires_intervention is True
    assert decision.can_retry is True


def test_unsupported_grounding_after_budget_exhausted_asks_clarification():
    results = [_eval("grounding", "UNSUPPORTED", 0.1)]
    decision = DecisionEngine(max_attempts=2).decide(results, _risk(), _model_decision(), attempt_number=2)
    assert decision.action == ControlAction.ASK_CLARIFICATION
    assert decision.can_retry is False


def test_partially_supported_grounding_triggers_verify():
    results = [_eval("grounding", "PARTIALLY_SUPPORTED", 0.35)]
    decision = DecisionEngine().decide(results, _risk(), _model_decision(), attempt_number=1)
    assert decision.action == ControlAction.VERIFY


def test_low_confidence_fast_model_triggers_change_model():
    results = [_eval("response_confidence", "LOW")]
    decision = DecisionEngine(max_attempts=2).decide(results, _risk(), _model_decision(role="FAST"), attempt_number=1)
    assert decision.action == ControlAction.CHANGE_MODEL


def test_low_confidence_already_on_strong_model_does_not_escalate_further():
    results = [_eval("response_confidence", "LOW")]
    decision = DecisionEngine(max_attempts=2).decide(results, _risk(), _model_decision(role="STRONG"), attempt_number=1)
    assert decision.action != ControlAction.CHANGE_MODEL


def test_contradicted_factuality_triggers_regenerate_then_human_review():
    results = [_eval("factuality", "CONTRADICTED")]
    first = DecisionEngine(max_attempts=2).decide(results, _risk(), _model_decision(), attempt_number=1)
    assert first.action == ControlAction.REGENERATE
    second = DecisionEngine(max_attempts=2).decide(results, _risk(), _model_decision(), attempt_number=2)
    assert second.action == ControlAction.HUMAN_REVIEW


def test_high_risk_action_always_requires_human_review_regardless_of_grounding():
    policy = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    results = [_eval("action_risk", "HIGH_RISK"), _eval("grounding", "SUPPORTED", 0.9)]
    decision = DecisionEngine().decide(results, _risk(RiskSeverity.HIGH_RISK), _model_decision(role="STRONG", require_verification=True), attempt_number=1)
    assert decision.action == ControlAction.HUMAN_REVIEW
    assert decision.triggering_evaluator == "action_risk"


def test_model_router_required_verification_without_other_signals_still_verifies():
    decision = DecisionEngine().decide([], _risk(), _model_decision(require_verification=True), attempt_number=1)
    assert decision.action == ControlAction.VERIFY
