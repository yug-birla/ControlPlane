from controlplane.query_intelligence.fingerprint import (
    Actionability,
    CapabilityHint,
    Complexity,
    Intent,
    Sensitivity,
)
from controlplane.query_intelligence.rules import RuleBasedQueryProfiler


def test_sql_keyword_produces_sql_hint_and_data_requirement():
    fp = RuleBasedQueryProfiler().profile("What was our Q4 revenue?")
    assert CapabilityHint.SQL in fp.capability_hints
    assert "data_requirement" in fp.explanation


def test_policy_keyword_produces_rag_hint():
    fp = RuleBasedQueryProfiler().profile("According to our HR policy, can I take unpaid leave?")
    assert CapabilityHint.RAG in fp.capability_hints


def test_action_keyword_produces_action_request_and_high_impact():
    fp = RuleBasedQueryProfiler().profile("Please execute a refund for this customer.")
    assert fp.intent == Intent.ACTION_REQUEST
    assert fp.actionability == Actionability.AGENTIC
    assert CapabilityHint.AGENT in fp.capability_hints
    assert "actionability" in fp.explanation


def test_pii_keyword_produces_potential_pii_sensitivity():
    fp = RuleBasedQueryProfiler().profile("What is the customer's social security number?")
    assert fp.sensitivity == Sensitivity.POTENTIAL_PII
    assert "sensitivity" in fp.explanation


def test_no_keyword_match_falls_back_to_general_hint():
    fp = RuleBasedQueryProfiler().profile("hi")
    assert fp.capability_hints == [CapabilityHint.GENERAL]


def test_complexity_scales_with_word_count():
    short = RuleBasedQueryProfiler().profile("What time is it?")
    long_query = RuleBasedQueryProfiler().profile(
        "Given our recent performance across all regional markets, can you provide a "
        "detailed breakdown of which product lines contributed most to the decline "
        "and what corrective actions leadership should consider for next quarter?"
    )
    assert short.complexity == Complexity.LOW
    assert long_query.complexity == Complexity.HIGH


def test_action_keyword_as_a_topic_reference_is_not_agentic_regression():
    """PERMANENT REGRESSION TEST (found during Milestone 5's mandatory
    architecture audit -- the "semantic actionability false-positive"
    named explicitly in that milestone's known-issues list). "Refund" as
    a noun modifying "policy"/"document" ("the refund policy document")
    is a topic reference, not a command -- must not classify as an
    agentic action request. Root cause was a weak algorithm (keyword
    presence can't distinguish verb vs. noun usage), fixed with a
    syntactic-position check in controlplane/query_intelligence/rules.py,
    not by adding more exception keywords."""
    fp = RuleBasedQueryProfiler().profile(
        "What was our Q4 revenue and according to the refund policy document what are cancellation terms?"
    )
    assert fp.actionability == Actionability.INFORMATIONAL
    assert fp.intent != Intent.ACTION_REQUEST

    fp2 = RuleBasedQueryProfiler().profile("What is the refund policy for cancelled subscriptions?")
    assert fp2.actionability == Actionability.INFORMATIONAL


def test_action_keyword_as_a_real_command_still_triggers_agentic():
    # The fix above must not blunt real agentic detection.
    fp = RuleBasedQueryProfiler().profile("Please process the refund for customer 123 immediately, execute it now.")
    assert fp.actionability == Actionability.AGENTIC
    assert fp.intent == Intent.ACTION_REQUEST


def test_every_rule_based_field_has_an_explanation_or_deterministic_default():
    fp = RuleBasedQueryProfiler().profile("What was our Q4 revenue?")
    # Rules baseline must be explainable (bootstrap SS8) -- every non-list
    # field that isn't the plain default has a stated reason.
    assert fp.source == "rules"
    assert isinstance(fp.explanation, dict)
    assert len(fp.explanation) > 0
