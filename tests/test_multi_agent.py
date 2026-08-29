"""Multi-agent composition governance.

The property under test: a chain can be individually safe but
collectively unsafe. Per-step AgentGate decisions cannot see this.
"""

from __future__ import annotations

from controlplane.governance.multi_agent import (
    AgentIdentity,
    AgentMessage,
    AgentMessageType,
    AgentRole,
    AgentStep,
    CompositionGovernor,
    CompositionRisk,
    DataSensitivity,
    DestinationClass,
)

_RETRIEVER = AgentIdentity("agent_a", AgentRole.RETRIEVER, permissions=frozenset({"read:enterprise_db"}))
_NOTIFIER = AgentIdentity("agent_b", AgentRole.NOTIFIER, parent_agent="agent_a",
                          permissions=frozenset({"send:notification"}))


def test_individually_allowed_steps_can_compose_into_a_critical_exfiltration_path():
    """THE case this module exists for. Agent A reads confidential data
    (ALLOW, read-only). Agent B sends externally (ALLOW, permitted).
    Neither step is wrong; the composition is."""
    steps = [
        AgentStep(_RETRIEVER, "sql_read_query", "ALLOW",
                  data_sensitivity=DataSensitivity.CONFIDENTIAL),
        AgentStep(_NOTIFIER, "send_notification", "ALLOW",
                  destination=DestinationClass.EXTERNAL),
    ]
    assessment = CompositionGovernor().evaluate(steps)

    assert assessment.risk is CompositionRisk.CRITICAL
    assert assessment.sensitive_data_reached_external
    assert assessment.recommended_action == "BLOCK"
    assert assessment.agent_chain == ["agent_a", "agent_b"]
    # Every individual step was ALLOW -- proving per-step gating misses this.
    assert all(s.governance_action == "ALLOW" for s in steps)


def test_sensitive_data_with_no_external_destination_is_not_critical():
    steps = [
        AgentStep(_RETRIEVER, "sql_read_query", "ALLOW",
                  data_sensitivity=DataSensitivity.CONFIDENTIAL),
        AgentStep(_NOTIFIER, "write_report", "ALLOW",
                  destination=DestinationClass.INTERNAL),
    ]
    assessment = CompositionGovernor().evaluate(steps)
    assert assessment.risk is not CompositionRisk.CRITICAL
    assert not assessment.sensitive_data_reached_external


def test_external_send_BEFORE_sensitive_access_is_not_an_exfiltration_path():
    """Ordering matters. Sending externally and only afterwards reading
    sensitive data does not leak that data -- flagging it would be a
    false positive that trains operators to ignore the signal."""
    steps = [
        AgentStep(_NOTIFIER, "send_notification", "ALLOW",
                  destination=DestinationClass.EXTERNAL),
        AgentStep(_RETRIEVER, "sql_read_query", "ALLOW",
                  data_sensitivity=DataSensitivity.CONFIDENTIAL),
    ]
    assessment = CompositionGovernor().evaluate(steps)
    assert not assessment.sensitive_data_reached_external
    assert assessment.risk is not CompositionRisk.CRITICAL


def test_a_blocked_step_cannot_create_an_exfiltration_path():
    """A step the system already prevented has moved no data. Counting it
    would manufacture a risk that governance successfully stopped."""
    steps = [
        AgentStep(_RETRIEVER, "sql_read_query", "ALLOW",
                  data_sensitivity=DataSensitivity.CONFIDENTIAL),
        AgentStep(_NOTIFIER, "send_notification", "BLOCK",
                  destination=DestinationClass.EXTERNAL, executed=False),
    ]
    assessment = CompositionGovernor().evaluate(steps)
    assert not assessment.sensitive_data_reached_external
    assert assessment.risk is not CompositionRisk.CRITICAL


def test_broad_accumulated_authority_across_agents_is_flagged_for_review():
    """No single agent holds the combined authority, so no single gate
    ever evaluated it."""
    a = AgentIdentity("a", AgentRole.RETRIEVER, permissions=frozenset({"read:enterprise_db"}))
    b = AgentIdentity("b", AgentRole.ANALYST, parent_agent="a",
                      permissions=frozenset({"execute:tools", "write:reports"}))
    steps = [
        AgentStep(a, "sql_read_query", "ALLOW"),
        AgentStep(b, "write_report", "ALLOW"),
    ]
    assessment = CompositionGovernor().evaluate(steps)
    assert assessment.risk is CompositionRisk.ELEVATED
    assert assessment.recommended_action == "HUMAN_REVIEW"
    assert len(assessment.cumulative_permissions) == 3


def test_a_benign_single_agent_chain_is_not_flagged():
    steps = [AgentStep(_RETRIEVER, "sql_read_query", "ALLOW")]
    assessment = CompositionGovernor().evaluate(steps)
    assert assessment.risk is CompositionRisk.NONE
    assert assessment.recommended_action == "ALLOW"


def test_empty_chain_is_handled_without_inventing_risk():
    assessment = CompositionGovernor().evaluate([])
    assert assessment.risk is CompositionRisk.NONE


def test_agent_lineage_is_preserved_for_permission_lineage():
    """USER -> AGENT -> ... requires knowing who spawned whom."""
    assert _NOTIFIER.parent_agent == "agent_a"
    assert _RETRIEVER.parent_agent is None


def test_agent_messages_are_structured_data_not_direct_calls():
    """Agents communicate THROUGH ControlPlane. A message is data that
    can be recorded, governed, and acted on -- never a direct call that
    bypasses governance."""
    message = AgentMessage(
        message_type=AgentMessageType.REPLAN_REQUEST,
        from_agent="agent_a", to_agent=None,
        payload_summary="cannot answer with current capabilities; needs structured data",
    )
    as_dict = message.to_dict()
    assert as_dict["message_type"] == "REPLAN_REQUEST"
    assert as_dict["to_agent"] is None  # addressed to ControlPlane, not a peer


def test_replan_request_is_a_request_not_a_mutation():
    """An agent may ask for a new plan; it must not be able to change one.
    The type carries no plan payload at all -- there is nothing for an
    agent to mutate."""
    message = AgentMessage(
        message_type=AgentMessageType.REPLAN_REQUEST,
        from_agent="agent_a", to_agent=None, payload_summary="evidence insufficient",
    )
    assert not hasattr(message, "new_plan")
    assert not hasattr(message, "graph")


def test_a_gatherer_agents_capability_determines_its_data_sensitivity_regression():
    """Regression: a gatherer agent reading the enterprise database emitted
    proposed_tool="sql_read", which matched nothing in the tool tables, so
    the chain scored PUBLIC and the gather-then-notify exfiltration path
    would NOT have fired.

    The composition governor was working correctly; it was being fed a tool
    name it had never heard of. Found by tracing a full multi-agent run
    end-to-end, not by a unit test of the governor."""
    from controlplane.governance.multi_agent import steps_from_agent_results

    steps = steps_from_agent_results([
        ("agent_analyst", {"proposed_tool": "sql_read", "serves_capability": "SQL",
                            "governance_action": "ALLOW", "execution_status": "EXECUTED"}),
        ("agent_action", {"proposed_tool": "send_notification",
                           "governance_action": "ALLOW", "execution_status": "EXECUTED"}),
    ])
    assert steps[0].data_sensitivity is DataSensitivity.CONFIDENTIAL
    assert steps[1].destination is DestinationClass.EXTERNAL

    assessment = CompositionGovernor().evaluate(steps)
    assert assessment.risk is CompositionRisk.CRITICAL
    assert assessment.sensitive_data_reached_external
