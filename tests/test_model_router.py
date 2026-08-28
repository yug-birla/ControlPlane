from controlplane.policy.baseline import PolicyBaseline
from controlplane.query_intelligence.fingerprint import (
    Actionability,
    Ambiguity,
    Complexity,
    Impact,
    Intent,
    QueryFingerprint,
    Sensitivity,
)
from controlplane.risk.profile import RiskProfile, RiskSeverity, ControlDepth
from controlplane.routing.model_router import ModelRouteAction, ModelRouter


def _fp(complexity=Complexity.LOW, impact=Impact.LOW, actionability=Actionability.INFORMATIONAL) -> QueryFingerprint:
    return QueryFingerprint(
        intent=Intent.INFORMATIONAL,
        complexity=complexity,
        sensitivity=Sensitivity.NONE,
        ambiguity=Ambiguity.LOW,
        impact=impact,
        actionability=actionability,
    )


def _risk(severity: RiskSeverity) -> RiskProfile:
    dims = {d: RiskSeverity.NO_ACTION for d in
            ("factuality", "reasoning", "privacy", "pii", "security", "bias", "financial", "action", "safety")}
    return RiskProfile(risk_dimensions=dims, severity=severity, recommended_control_depth=ControlDepth.FAST_PATH)


def test_low_complexity_low_risk_uses_fast_model_no_verification():
    decision = ModelRouter().decide(_fp(complexity=Complexity.LOW), _risk(RiskSeverity.NO_ACTION), PolicyBaseline().decide(RiskSeverity.NO_ACTION))
    assert decision.action == ModelRouteAction.USE_FAST_MODEL
    assert decision.model_role == "FAST"
    assert decision.require_verification is False


def test_high_complexity_escalates_to_strong_model():
    decision = ModelRouter().decide(_fp(complexity=Complexity.HIGH), _risk(RiskSeverity.NO_ACTION), PolicyBaseline().decide(RiskSeverity.NO_ACTION))
    assert decision.action == ModelRouteAction.USE_STRONG_MODEL
    assert decision.model_role == "STRONG"


def test_high_impact_escalates_to_strong_model_with_verification():
    decision = ModelRouter().decide(_fp(impact=Impact.HIGH), _risk(RiskSeverity.NO_ACTION), PolicyBaseline().decide(RiskSeverity.NO_ACTION))
    assert decision.action == ModelRouteAction.USE_STRONG_MODEL
    assert decision.require_verification is True


def test_high_risk_policy_tier_requires_human_review_regardless_of_complexity():
    policy = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    decision = ModelRouter().decide(_fp(complexity=Complexity.LOW), _risk(RiskSeverity.HIGH_RISK), policy)
    assert decision.action == ModelRouteAction.HUMAN_REVIEW
    assert decision.model_role == "STRONG"
    assert decision.require_verification is True
    assert decision.human_approval_required is True


def test_agentic_request_with_agent_restricted_abstains():
    """AGENT is only policy-restricted at CRITICAL_ACTION now (changed
    this milestone -- see controlplane/policy/baseline.py: a real
    per-tool AgentGate exists, so HIGH_RISK no longer needs a blanket
    policy-level cutoff)."""
    policy = PolicyBaseline().decide(RiskSeverity.CRITICAL)
    assert "AGENT" in policy.restricted_capabilities
    decision = ModelRouter().decide(
        _fp(actionability=Actionability.AGENTIC, impact=Impact.CRITICAL), _risk(RiskSeverity.CRITICAL), policy
    )
    assert decision.action == ModelRouteAction.ABSTAIN
    assert decision.model_role is None


def test_agentic_request_with_agent_not_restricted_does_not_abstain():
    policy = PolicyBaseline().decide(RiskSeverity.LOW_RISK)
    assert "AGENT" not in policy.restricted_capabilities
    decision = ModelRouter().decide(
        _fp(actionability=Actionability.AGENTIC, impact=Impact.LOW), _risk(RiskSeverity.LOW_RISK), policy
    )
    assert decision.action != ModelRouteAction.ABSTAIN


def test_high_risk_agentic_request_no_longer_abstains_reaches_the_real_gate_instead():
    """Regression-preventing companion to the CRITICAL-only test above:
    a HIGH_RISK agentic request must now flow through to the real
    AgentCapability/AgentGate path (controlplane/capabilities/agent_capability.py),
    not be abstained from wholesale."""
    policy = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    assert "AGENT" not in policy.restricted_capabilities
    decision = ModelRouter().decide(
        _fp(actionability=Actionability.AGENTIC, impact=Impact.HIGH), _risk(RiskSeverity.HIGH_RISK), policy
    )
    assert decision.action != ModelRouteAction.ABSTAIN


def test_reason_is_always_populated():
    decision = ModelRouter().decide(_fp(), _risk(RiskSeverity.NO_ACTION), PolicyBaseline().decide(RiskSeverity.NO_ACTION))
    assert decision.reason


def test_qp190_style_high_risk_governance_case_never_reaches_fast_model_unverified():
    """Defense-in-depth companion to
    tests/test_risk_profiler.py::test_qp190_governance_decision_support_regression --
    even hypothetically, if a future change to the Risk Profiler
    correctly (or incorrectly) reports HIGH_RISK for a decisional/
    governance query, the Model Router must never respond with
    USE_FAST_MODEL + no verification. This is the actual safety property
    the bootstrap SS63 regression requirement is protecting."""
    policy = PolicyBaseline().decide(RiskSeverity.HIGH_RISK)
    decision = ModelRouter().decide(
        _fp(complexity=Complexity.LOW, actionability=Actionability.DECISIONAL), _risk(RiskSeverity.HIGH_RISK), policy
    )
    assert decision.action != ModelRouteAction.USE_FAST_MODEL
    assert decision.require_verification is True
