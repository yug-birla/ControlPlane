from controlplane.decision.engine import ControlAction, ControlDecision
from controlplane.risk.profile import ControlDepth, RiskProfile, RiskSeverity
from controlplane.trust.engine import TrustEngine, TrustLevel
from controlplane.verification.engine import VerificationResult, VerificationStatus


def _risk(severity: RiskSeverity) -> RiskProfile:
    return RiskProfile(
        risk_dimensions={"action": severity}, severity=severity,
        recommended_control_depth=ControlDepth.FAST_PATH,
    )


def _decision(action: ControlAction = ControlAction.CONTINUE, attempt_number: int = 1) -> ControlDecision:
    return ControlDecision(action=action, reason="test", attempt_number=attempt_number, can_retry=False)


def test_first_pass_verified_low_risk_is_high_trust():
    result = TrustEngine().assess(
        verification=VerificationResult(status=VerificationStatus.VERIFIED, reason="ok", checked_evaluators=[]),
        decision=_decision(attempt_number=1),
        risk=_risk(RiskSeverity.NO_ACTION),
    )
    assert result.level == TrustLevel.HIGH


def test_rejected_verification_is_low_trust_even_with_low_risk():
    result = TrustEngine().assess(
        verification=VerificationResult(status=VerificationStatus.REJECTED, reason="needs human approval", checked_evaluators=[]),
        decision=_decision(action=ControlAction.HUMAN_REVIEW),
        risk=_risk(RiskSeverity.NO_ACTION),
    )
    assert result.level == TrustLevel.LOW


def test_verified_but_high_risk_is_capped_at_medium():
    result = TrustEngine().assess(
        verification=VerificationResult(status=VerificationStatus.VERIFIED, reason="ok", checked_evaluators=[]),
        decision=_decision(attempt_number=1),
        risk=_risk(RiskSeverity.HIGH_RISK),
    )
    assert result.level == TrustLevel.MEDIUM


def test_verified_after_a_retry_is_medium_not_high():
    result = TrustEngine().assess(
        verification=VerificationResult(status=VerificationStatus.VERIFIED, reason="ok", checked_evaluators=[]),
        decision=_decision(attempt_number=2),
        risk=_risk(RiskSeverity.NO_ACTION),
    )
    assert result.level == TrustLevel.MEDIUM


def test_not_verified_is_low_trust():
    result = TrustEngine().assess(
        verification=VerificationResult(status=VerificationStatus.NOT_VERIFIED, reason="grounding=UNSUPPORTED", checked_evaluators=[]),
        decision=_decision(action=ControlAction.ASK_CLARIFICATION),
        risk=_risk(RiskSeverity.NO_ACTION),
    )
    assert result.level == TrustLevel.LOW
