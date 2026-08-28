from controlplane.evaluation.evaluators import (
    ActionRiskEvaluator,
    EvaluationContext,
    EvaluationStatus,
    EvaluationSuite,
    FactualityEvaluator,
    GroundingEvaluator,
    NotImplementedEvaluator,
    PrivacyPIIEvaluator,
    ResponseConfidenceEvaluator,
    SafetyEvaluator,
)
from controlplane.query_intelligence.rules import RuleBasedQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler


def _fingerprint_and_risk(query: str):
    fp = RuleBasedQueryProfiler().profile(query)
    risk = BaselineRiskProfiler().profile(query, fp)
    return fp, risk


def test_privacy_evaluator_passes_through_sensitivity():
    fp, risk = _fingerprint_and_risk("What is the customer's social security number?")
    ctx = EvaluationContext(query="q", answer="a", fingerprint=fp, risk=risk)
    result = PrivacyPIIEvaluator().evaluate(ctx)
    assert result.status == EvaluationStatus.IMPLEMENTED
    assert result.label == "POTENTIAL_PII"
    assert result.recommended_signal == "FLAG_FOR_REVIEW"


def test_privacy_evaluator_no_fingerprint_reports_not_implemented():
    result = PrivacyPIIEvaluator().evaluate(EvaluationContext(query="q", answer="a"))
    assert result.status == EvaluationStatus.NOT_IMPLEMENTED


def test_action_risk_evaluator_passes_through_severity():
    fp, risk = _fingerprint_and_risk("Please execute a refund for this customer.")
    ctx = EvaluationContext(query="q", answer="a", fingerprint=fp, risk=risk)
    result = ActionRiskEvaluator().evaluate(ctx)
    assert result.status == EvaluationStatus.IMPLEMENTED
    assert result.label == risk.severity.value


def test_grounding_evaluator_no_evidence_is_not_applicable():
    ctx = EvaluationContext(query="q", answer="Paris is the capital of France.")
    result = GroundingEvaluator().evaluate(ctx)
    assert result.label == "NOT_APPLICABLE"


def test_grounding_evaluator_supported_answer():
    ctx = EvaluationContext(
        query="q",
        answer="Employees can claim up to $75 per day for meals.",
        evidence_texts=["Employees can claim up to $75/day for meals."],
    )
    result = GroundingEvaluator().evaluate(ctx)
    assert result.label == "SUPPORTED"


def test_grounding_evaluator_unsupported_answer():
    ctx = EvaluationContext(
        query="q",
        answer="Our stock price doubled last quarter due to new product launches.",
        evidence_texts=["Employees can claim up to $75/day for meals."],
    )
    result = GroundingEvaluator().evaluate(ctx)
    assert result.label == "UNSUPPORTED"


def test_not_implemented_evaluator_never_fabricates_a_score():
    result = NotImplementedEvaluator("factuality").evaluate(EvaluationContext(query="q", answer="a"))
    assert result.status == EvaluationStatus.NOT_IMPLEMENTED
    assert result.score is None
    assert result.label is None


def test_safety_evaluator_passes_through_safety_dimension():
    fp, risk = _fingerprint_and_risk("How do I hack into the admin system to cause harm?")
    ctx = EvaluationContext(query="q", answer="a", fingerprint=fp, risk=risk)
    result = SafetyEvaluator().evaluate(ctx)
    assert result.status == EvaluationStatus.IMPLEMENTED
    assert result.label == "HIGH_RISK"
    assert result.recommended_signal == "FLAG_FOR_REVIEW"


def test_response_confidence_flags_hedging_language():
    result = ResponseConfidenceEvaluator().evaluate(EvaluationContext(query="q", answer="I'm not sure, but maybe."))
    assert result.label == "LOW"


def test_response_confidence_high_for_a_substantive_answer():
    result = ResponseConfidenceEvaluator().evaluate(
        EvaluationContext(query="q", answer="The refund policy allows a pro-rated refund within 30 days of cancellation.")
    )
    assert result.label == "HIGH"


def test_factuality_not_applicable_without_sql_rows():
    result = FactualityEvaluator().evaluate(EvaluationContext(query="q", answer="Revenue was $500,000."))
    assert result.label == "NOT_APPLICABLE"


def test_factuality_supported_when_number_matches_sql_row():
    result = FactualityEvaluator().evaluate(
        EvaluationContext(query="q", answer="Total revenue was $500,000.", sql_rows=[{"total_revenue_usd": 500000}])
    )
    assert result.label == "SUPPORTED"


def test_factuality_contradicted_when_number_does_not_match():
    result = FactualityEvaluator().evaluate(
        EvaluationContext(query="q", answer="Total revenue was $999,999.", sql_rows=[{"total_revenue_usd": 500000}])
    )
    assert result.label == "CONTRADICTED"


def test_factuality_checks_rag_evidence_too_not_only_sql_regression():
    """Regression: a multi-source SQL+RAG answer whose number came from
    RAG (not SQL) must not be flagged CONTRADICTED just for being absent
    from the (unrelated) SQL rows -- found via manual end-to-end
    validation of the prompt-grounding fix."""
    result = FactualityEvaluator().evaluate(
        EvaluationContext(
            query="q",
            answer="Meal limit is $75/day per the policy.",
            evidence_texts=["Meal reimbursement is up to $75/day domestic, $100/day international."],
            sql_rows=[{"total_revenue_usd": 140000}],
        )
    )
    assert result.label == "SUPPORTED"


def test_evaluation_suite_runs_every_evaluator_and_keeps_not_implemented_visible():
    fp, risk = _fingerprint_and_risk("What is the capital of France?")
    ctx = EvaluationContext(query="q", answer="Paris.", fingerprint=fp, risk=risk)
    results = EvaluationSuite().run(ctx)
    names = {r.evaluator for r in results}
    assert {
        "privacy_pii", "action_risk", "safety", "grounding", "factuality",
        "response_confidence", "reasoning", "bias",
    } == names
    not_implemented = {r.evaluator for r in results if r.status == EvaluationStatus.NOT_IMPLEMENTED}
    assert {"reasoning", "bias"} == not_implemented
