from controlplane.decision.engine import ControlAction, ControlDecision
from controlplane.evaluation.evaluators import EvaluationResult, EvaluationStatus
from controlplane.verification.engine import VerificationEngine, VerificationStatus


def _decision(action=ControlAction.CONTINUE) -> ControlDecision:
    return ControlDecision(action=action, reason="test", attempt_number=1, can_retry=False)


def _eval(name, label):
    return EvaluationResult(evaluator=name, status=EvaluationStatus.IMPLEMENTED, label=label, rationale="test")


def test_no_concerns_is_verified():
    result = VerificationEngine().verify([_eval("grounding", "SUPPORTED")], _decision())
    assert result.status == VerificationStatus.VERIFIED


def test_unsupported_grounding_is_not_verified():
    result = VerificationEngine().verify([_eval("grounding", "UNSUPPORTED")], _decision())
    assert result.status == VerificationStatus.NOT_VERIFIED


def test_partially_supported_is_partially_verified():
    result = VerificationEngine().verify([_eval("grounding", "PARTIALLY_SUPPORTED")], _decision())
    assert result.status == VerificationStatus.PARTIALLY_VERIFIED


def test_human_review_decision_is_rejected_not_verified():
    result = VerificationEngine().verify([_eval("grounding", "SUPPORTED")], _decision(ControlAction.HUMAN_REVIEW))
    assert result.status == VerificationStatus.REJECTED


def test_ask_clarification_decision_is_not_verified():
    result = VerificationEngine().verify([], _decision(ControlAction.ASK_CLARIFICATION))
    assert result.status == VerificationStatus.NOT_VERIFIED


def test_low_confidence_blocks_verification():
    result = VerificationEngine().verify([_eval("response_confidence", "LOW")], _decision())
    assert result.status == VerificationStatus.NOT_VERIFIED
