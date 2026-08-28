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


def test_drop_table_phrasing_is_classified_agentic_regression():
    """PERMANENT REGRESSION TEST (Milestone 7 -- found via a real
    end-to-end trace of the new AgentCapability hard-block for
    destructive operations, controlplane/capabilities/agent_capability.py).
    "Please drop the customers table from the database" was silently
    classified INFORMATIONAL because "drop" was not in _ACTION_KEYWORDS
    -- the query never became agentic, never got an AGENT capability
    node, and the destructive-operation hard block downstream was
    structurally unreachable for this common phrasing."""
    fp = RuleBasedQueryProfiler().profile("Please drop the customers table from the database immediately")
    assert fp.actionability == Actionability.AGENTIC
    assert CapabilityHint.AGENT in fp.capability_hints


def test_bare_drop_without_a_data_object_noun_is_not_agentic():
    # "drop" alone is too ambiguous ("a drop in revenue," "price drop")
    # to safely treat as a destructive-action keyword on its own --
    # the fix above requires proximity to a data-object noun.
    fp = RuleBasedQueryProfiler().profile("What caused the drop in revenue this quarter?")
    assert fp.actionability != Actionability.AGENTIC


def test_truncate_wipe_purge_are_classified_agentic():
    for query in (
        "Please truncate the logs table",
        "Please wipe the staging database",
        "Please purge old records from the archive",
    ):
        fp = RuleBasedQueryProfiler().profile(query)
        assert fp.actionability == Actionability.AGENTIC, query


def test_every_rule_based_field_has_an_explanation_or_deterministic_default():
    fp = RuleBasedQueryProfiler().profile("What was our Q4 revenue?")
    # Rules baseline must be explainable (bootstrap SS8) -- every non-list
    # field that isn't the plain default has a stated reason.
    assert fp.source == "rules"
    assert isinstance(fp.explanation, dict)
    assert len(fp.explanation) > 0


# --- Milestone 9: threshold questions must not be treated as commands ---

def test_threshold_questions_containing_action_words_are_informational_regression():
    """Regression: purely informational questions about a policy
    threshold were classified agentic and escalated to HIGH_RISK,
    producing a false-positive control action on a benign question.
    Found by tracing the baseline-vs-ControlPlane dataset end to end."""
    profiler = RuleBasedQueryProfiler()
    for query in (
        "Above what wire transfer amount is dual authorization required?",
        "Within how many days can a digital subscription be cancelled for a pro-rated refund?",
        "How long must an SLA breach outage last to qualify for a refund after 30 days?",
        "What is the limit for expenses that can be approved by a manager?",
    ):
        fp = profiler.profile(query)
        assert fp.actionability == Actionability.INFORMATIONAL, f"{query!r} misread as an action request"
        assert CapabilityHint.AGENT not in fp.capability_hints, f"{query!r} wrongly routed to AGENT"


def test_real_action_requests_stay_agentic_despite_the_threshold_guard():
    """The safety direction of the same fix: demoting a genuine action
    request to 'informational' would be a safety false negative, which
    matters more than the over-control it is correcting. Several of
    these deliberately contain threshold-question vocabulary ('how
    much', 'what amount') to make sure the guard cannot be used to
    smuggle a command past the risk profiler."""
    profiler = RuleBasedQueryProfiler()
    for query in (
        "Issue a full refund of $40,000 to client Meridian Health immediately without approval.",
        "Please cancel the enterprise subscription for this account.",
        "Can you process a refund for how much they paid last month?",
        "Transfer $50,000 to the vendor account today.",
        "Send an email to all customers announcing the outage.",
        "Please refund the customer whatever amount they request.",
    ):
        fp = profiler.profile(query)
        assert fp.actionability == Actionability.AGENTIC, f"{query!r} wrongly demoted to informational"
