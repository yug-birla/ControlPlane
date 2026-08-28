from controlplane.policy.baseline import PolicyBaseline, PolicyTier
from controlplane.risk.profile import RiskSeverity


def test_low_risk_requires_no_controls():
    decision = PolicyBaseline().decide(RiskSeverity.NO_ACTION)
    assert decision.tier == PolicyTier.LOW_RISK
    assert decision.required_verification is False
    assert decision.human_approval_required is False
    assert decision.restricted_capabilities == []


def test_high_risk_requires_verification_and_human_approval():
    decision = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    assert decision.tier == PolicyTier.HIGH_RISK
    assert decision.required_verification is True
    assert decision.human_approval_required is True


def test_high_risk_no_longer_blanket_restricts_agent():
    """Changed this milestone: a real per-tool AgentGate now exists
    (controlplane/capabilities/agent_capability.py), so a HIGH_RISK
    agentic request reaches that graduated gate instead of being
    removed from the route wholesale. See controlplane/policy/baseline.py."""
    decision = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    assert "AGENT" not in decision.restricted_capabilities


def test_critical_action_is_the_true_hard_ceiling_for_agent():
    decision = PolicyBaseline().decide(RiskSeverity.CRITICAL)
    assert "AGENT" in decision.restricted_capabilities
    assert "SQL" in decision.restricted_capabilities


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
