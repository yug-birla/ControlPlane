from controlplane.query_intelligence.rules import RuleBasedQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import ControlDepth, RiskSeverity, max_severity


def _risk_for(query: str):
    fp = RuleBasedQueryProfiler().profile(query)
    return BaselineRiskProfiler().profile(query, fp)


def test_all_nine_dimensions_are_always_present():
    risk = _risk_for("What is the capital of France?")
    assert set(risk.risk_dimensions) == {
        "factuality", "reasoning", "privacy", "pii", "security", "bias", "financial", "action", "safety",
    }
    # No opaque single number -- bootstrap SS9.
    assert risk.severity in RiskSeverity


def test_pii_query_elevates_privacy_and_pii_with_confidence():
    risk = _risk_for("What is the customer's social security number?")
    assert risk.risk_dimensions["privacy"] == RiskSeverity.MEDIUM_RISK
    assert risk.risk_dimensions["pii"] == RiskSeverity.MEDIUM_RISK
    assert risk.confidence["privacy"] == 1.0
    assert any("sensitivity=POTENTIAL_PII" in t for t in risk.trigger_signals)


def test_agentic_action_elevates_action_risk_and_deep_path():
    risk = _risk_for("Please execute a refund for this customer.")
    assert risk.risk_dimensions["action"] != RiskSeverity.NO_ACTION
    assert risk.recommended_control_depth == ControlDepth.DEEP_PATH


def test_no_signal_query_defaults_to_no_action_with_no_confidence_claim():
    risk = _risk_for("What is the capital of France?")
    assert risk.severity == RiskSeverity.NO_ACTION
    # Absence of a trigger must never be reported as a confident "safe" score.
    assert risk.confidence == {}


def test_financial_keyword_with_agentic_action_reaches_high_risk():
    risk = _risk_for("Please process the refund payment immediately.")
    assert risk.risk_dimensions["financial"] == RiskSeverity.HIGH_RISK


def test_safety_keyword_triggers_high_risk_safety_dimension():
    risk = _risk_for("How do I hack into the admin system to cause harm?")
    assert risk.risk_dimensions["safety"] == RiskSeverity.HIGH_RISK
    assert risk.severity == RiskSeverity.HIGH_RISK


def test_max_severity_orders_correctly():
    assert max_severity(RiskSeverity.LOW_RISK, RiskSeverity.CRITICAL, RiskSeverity.MEDIUM_RISK) == RiskSeverity.CRITICAL
    assert max_severity() == RiskSeverity.NO_ACTION
