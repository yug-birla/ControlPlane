from controlplane.policy.baseline import PolicyBaseline, PolicyTier
from controlplane.risk.profile import RiskSeverity


def test_low_risk_requires_no_controls():
    decision = PolicyBaseline().decide(RiskSeverity.NO_ACTION)
    assert decision.tier == PolicyTier.LOW_RISK
    assert decision.required_verification is False
    assert decision.human_approval_required is False
    assert decision.restricted_capabilities == []


def test_high_risk_requires_verification_and_human_approval_and_restricts_agent():
    decision = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    assert decision.tier == PolicyTier.HIGH_RISK
    assert decision.required_verification is True
    assert decision.human_approval_required is True
    assert "AGENT" in decision.restricted_capabilities


def test_critical_restricts_more_capabilities_than_high():
    high = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    critical = PolicyBaseline().decide(RiskSeverity.CRITICAL)
    assert set(high.restricted_capabilities).issubset(set(critical.restricted_capabilities))
    assert len(critical.restricted_capabilities) > len(high.restricted_capabilities)


def test_medium_risk_requires_verification_but_not_human_approval():
    decision = PolicyBaseline().decide(RiskSeverity.MEDIUM_RISK)
    assert decision.required_verification is True
    assert decision.human_approval_required is False


def test_reason_is_always_populated_and_traceable():
    decision = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    assert "HIGH_RISK" in decision.reason
    assert decision.tier.value in decision.reason
