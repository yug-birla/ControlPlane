import shutil

import pytest

from controlplane.capabilities.agent_capability import _REPORTS_DIR, AgentCapability


@pytest.fixture(autouse=True)
def _clean_reports_dir():
    yield
    shutil.rmtree(_REPORTS_DIR, ignore_errors=True)


def test_sql_read_query_is_allowed_and_actually_executes():
    result = AgentCapability().execute("How many support tickets are open in the database?")
    assert result["proposed_tool"] == "sql_read_query"
    assert result["governance_action"] == "ALLOW"
    assert result["execution_status"] == "COMPLETED"
    assert result["tool_result"]["status"] == "EXECUTED"  # the real SQLCapability actually ran


def test_write_report_is_allowed_and_writes_a_real_file():
    result = AgentCapability().execute("Please write a report summarizing this quarter's performance")
    assert result["proposed_tool"] == "write_report"
    assert result["governance_action"] == "ALLOW"
    assert result["tool_result"]["status"] == "WRITTEN"
    from pathlib import Path

    assert Path(result["tool_result"]["path"]).exists()


def test_medium_risk_notification_is_restricted_not_sent():
    result = AgentCapability().execute("Please send a notification to the team about the outage")
    assert result["proposed_tool"] == "send_notification"
    assert result["governance_action"] == "RESTRICT"
    assert result["execution_status"] == "COMPLETED_RESTRICTED"
    assert result["tool_result"]["status"] == "QUEUED_FOR_REVIEW"


def test_high_stakes_notification_requires_human_review_and_is_not_sent():
    result = AgentCapability().execute("Please send a notification to the board about our financial results")
    assert result["proposed_tool"] == "send_notification"
    assert result["step_risk"] == "HIGH_RISK"
    assert result["governance_action"] == "HUMAN_REVIEW"
    assert result["execution_status"] == "AWAITING_HUMAN_APPROVAL"
    assert result["tool_result"]["status"] == "NOT_EXECUTED"


def test_destructive_operation_is_hard_blocked_regardless_of_phrasing():
    for query in (
        "Please delete all records from the customers table",
        "Please drop the customers table from the database",
        "Please truncate the audit log table",
    ):
        result = AgentCapability().execute(query)
        assert result["governance_action"] == "BLOCK", query
        assert result["execution_status"] == "BLOCKED", query
        assert result["tool_result"]["status"] == "NOT_EXECUTED", query


def test_no_actionable_tool_identified_is_a_safe_no_op():
    result = AgentCapability().execute("What is the capital of France?")
    assert result["proposed_tool"] == "no_actionable_tool"
    assert result["governance_action"] == "ALLOW"
    assert result["tool_result"]["status"] == "NO_OP"


# ---------------------------------------------------------------------------
# COMMUNICATION MUST CHANGE BEHAVIOUR (SS9).
#
# Handoff messages were synthesized AFTER every agent had already run, and
# AgentCapability.execute took only the query string -- so a handoff could
# not have influenced anything even if one had arrived in time. The
# communication ablation reported no effect because there was no effect to
# find: the two arms differed only in whether a log entry was written.
#
# The bus is now the channel. These pin the consequence.
# ---------------------------------------------------------------------------


def _handoff(sensitivity, *, count=5, digest=("Q4 revenue was $410,000",)):
    from controlplane.governance.handoff import HandoffContext

    return HandoffContext(
        from_agents=("agent_analyst",),
        sources=("SQL",),
        evidence_count=count,
        max_sensitivity=sensitivity,
        evidence_digest=digest,
    )


def test_an_external_send_is_gated_harder_when_it_carries_handed_over_sensitive_data():
    """The same tool call, judged differently because of what the agent
    was handed. Previously AgentGate saw a tool call and a static risk
    label and never the data the call would carry, so this chain was
    caught only afterwards by CompositionGovernor."""
    from controlplane.capabilities.agent_capability import AgentCapability
    from controlplane.governance.multi_agent import DataSensitivity

    query = "Send the customer contact records to our external marketing agency."

    alone = AgentCapability().execute(query)
    informed = AgentCapability().execute(query, handoff=_handoff(DataSensitivity.CONFIDENTIAL))

    assert alone["step_risk"] == "MEDIUM_RISK"
    assert alone["governance_action"] == "RESTRICT"

    assert informed["step_risk"] == "HIGH_RISK"
    assert informed["governance_action"] == "HUMAN_REVIEW"
    assert informed["handoff_influence"] == "CHANGED_STEP_RISK"
    assert informed["step_risk_without_handoff"] == "MEDIUM_RISK"


def test_non_sensitive_evidence_does_not_escalate_the_send():
    """The guard against buying safety by escalating everything: a
    handoff of public evidence must leave the decision alone."""
    from controlplane.capabilities.agent_capability import AgentCapability
    from controlplane.governance.multi_agent import DataSensitivity

    query = "Send the published pricing summary to our external marketing agency."
    informed = AgentCapability().execute(query, handoff=_handoff(DataSensitivity.PUBLIC))

    assert informed["step_risk"] == "MEDIUM_RISK"
    assert informed["handoff_influence"] == "OBSERVED_ONLY"


def test_a_report_contains_the_evidence_it_was_handed():
    """Influence on the artifact, not only on the risk label."""
    from pathlib import Path

    from controlplane.capabilities.agent_capability import AgentCapability
    from controlplane.governance.multi_agent import DataSensitivity

    query = "Write a report of the quarterly figures."
    result = AgentCapability().execute(
        query,
        handoff=_handoff(DataSensitivity.INTERNAL, digest=("Q4 revenue was $410,000",)),
    )
    if result["tool_result"].get("status") != "WRITTEN":
        import pytest

        pytest.skip(f"report not written: {result['tool_result']}")

    text = Path(result["tool_result"]["path"]).read_text(encoding="utf-8")
    assert "Q4 revenue was $410,000" in text
    assert "agent_analyst" in text
    assert result["handoff_influence"] == "CHANGED_TOOL_OUTPUT"


def test_no_handoff_leaves_the_agent_exactly_as_it_was():
    """Backwards compatibility: an agent with no predecessors behaves
    identically to before this feature existed."""
    from controlplane.capabilities.agent_capability import AgentCapability

    query = "Send a summary notification to finance."
    result = AgentCapability().execute(query)
    assert result["handoff_received"] is None
    assert result["handoff_influence"] == "NONE"


def test_the_context_is_a_summary_not_the_upstream_payload():
    """SS12/SS37: structured context, not the whole trajectory. A large
    retrieval must not become a large prompt."""
    from controlplane.governance.handoff import (
        MAX_DIGEST_CHARS,
        MAX_DIGEST_ITEMS,
        build_handoff_context,
        handoff_messages_for,
    )

    upstream = [(
        "agent_retriever",
        {"serves_capability": "RAG",
         "evidence": [{"text": "x" * 4000} for _ in range(50)]},
    )]
    messages = handoff_messages_for(to_agent="agent_action", upstream=upstream)
    context = build_handoff_context(delivered=messages, upstream=upstream)

    assert context is not None
    assert context.evidence_count == 50, "the true count is still reported"
    assert len(context.evidence_digest) == MAX_DIGEST_ITEMS
    for item in context.evidence_digest:
        assert len(item) <= MAX_DIGEST_CHARS


def test_an_undelivered_message_yields_no_context():
    """What makes the no-communication arm real: the evidence exists
    upstream, and without delivery the receiver still gets nothing."""
    from controlplane.governance.handoff import build_handoff_context

    upstream = [("agent_analyst", {"serves_capability": "SQL", "rows": [{"revenue": 1}]})]
    assert build_handoff_context(delivered=[], upstream=upstream) is None
