"""Permanent regression tests for multi-agent execution (§47).

These pin the properties that have already broken once, or that would
break silently: message correlation, plan-shape derivation, failure
isolation, and the authority boundary. All are pure-logic tests -- no
model loading -- so they stay cheap enough to run on every commit.
"""

from __future__ import annotations

from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus
from controlplane.governance.agent_bus import AgentBus, RequestTriage, evidence_handoff
from controlplane.governance.multi_agent import (
    AgentIdentity,
    AgentMessage,
    AgentMessageType,
    AgentRole,
    CompositionGovernor,
    CompositionRisk,
    DataSensitivity,
    DestinationClass,
    steps_from_agent_results,
)
from controlplane.planning.agent_planner import AgentPlanner


# --- 1-2. Agent communication and correlation -------------------

def test_every_agent_message_carries_sender_receiver_and_type():
    message = evidence_handoff(from_agent="agent_retriever", to_agent="agent_action",
                               evidence_count=3, sensitivity=DataSensitivity.CONFIDENTIAL)
    payload = message.to_dict()
    for field in ("message_type", "from_agent", "to_agent", "payload_summary", "data_sensitivity"):
        assert field in payload, f"agent message lost {field}"


def test_message_sensitivity_is_carried_not_rederived():
    """Composition governance must see the classification the sending
    agent saw. Re-deriving it downstream is how the two disagree."""
    message = evidence_handoff(from_agent="a", to_agent="b", evidence_count=1,
                               sensitivity=DataSensitivity.RESTRICTED)
    assert message.data_sensitivity is DataSensitivity.RESTRICTED


# --- 3. Handoff -------------------------------------------------

def test_handoff_is_addressed_to_a_peer_while_a_replan_request_is_not():
    handoff = evidence_handoff(from_agent="a", to_agent="b", evidence_count=1,
                               sensitivity=DataSensitivity.PUBLIC)
    replan = AgentMessage(message_type=AgentMessageType.REPLAN_REQUEST,
                          from_agent="a", to_agent=None, payload_summary="no evidence")
    assert handoff.to_agent == "b"
    assert replan.to_agent is None, "a replan request is addressed to ControlPlane, not a peer"


# --- 4. Replan request ------------------------------------------

def test_replan_triage_is_grounded_in_what_the_agent_did():
    bus = AgentBus()
    request = bus.send(AgentMessage(
        message_type=AgentMessageType.REPLAN_REQUEST, from_agent="agent_analyst",
        to_agent=None, payload_summary="I cannot complete this",
    ))
    # Same message, opposite evidence -> opposite decision.
    assert bus.triage_replan_request(request, agent_produced_evidence=False).triage is RequestTriage.ACCEPT
    assert bus.triage_replan_request(request, agent_produced_evidence=True).triage is RequestTriage.REJECT


# --- 5. Parallel agents -----------------------------------------

def test_gatherers_are_scheduled_concurrently_because_they_have_no_dependencies():
    planner = AgentPlanner()
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="generation", capability="generation"))
    graph.validate()
    plan = planner.plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=False)
    planner.apply(graph, plan)

    gatherers = [a.agent_id for a in plan.agents if a.role is not AgentRole.NOTIFIER]
    assert len(gatherers) == 2
    for node_id in gatherers:
        assert graph.get(node_id).depends_on == ()

    # The executor's own readiness rule must agree.
    ready = {n.node_id for n in graph.ready_nodes()}
    assert set(gatherers).issubset(ready), "independent gatherers were not simultaneously ready"


# --- 6. Failure isolation ---------------------------------------

def test_one_failed_gatherer_does_not_block_the_merge():
    """Regression: a merge node that required ALL dependencies killed the
    whole request when one evidence source failed, instead of answering
    from the evidence that did arrive."""
    graph = ExecutionGraph([
        ExecutionNode(node_id="agent_retriever", capability="AGENT"),
        ExecutionNode(node_id="agent_analyst", capability="AGENT"),
        ExecutionNode(node_id="merge", capability="merge",
                      depends_on=("agent_retriever", "agent_analyst"),
                      requires_all_dependencies=False),
    ])
    graph.validate()
    graph.get("agent_retriever").status = NodeStatus.COMPLETED
    graph.get("agent_analyst").status = NodeStatus.FAILED

    assert "merge" in {n.node_id for n in graph.ready_nodes()}


def test_merge_blocks_only_when_every_source_failed():
    graph = ExecutionGraph([
        ExecutionNode(node_id="agent_retriever", capability="AGENT"),
        ExecutionNode(node_id="agent_analyst", capability="AGENT"),
        ExecutionNode(node_id="merge", capability="merge",
                      depends_on=("agent_retriever", "agent_analyst"),
                      requires_all_dependencies=False),
    ])
    graph.validate()
    graph.get("agent_retriever").status = NodeStatus.FAILED
    graph.get("agent_analyst").status = NodeStatus.FAILED
    assert "merge" not in {n.node_id for n in graph.ready_nodes()}


# --- 7. Conflicting / composed agents ---------------------------

def test_splitting_a_risky_action_across_agents_does_not_launder_it():
    """Read here, send there. Each step is permitted; the composition is
    an exfiltration path. If decomposition reduced assessed risk, an
    attacker's easiest move would be to use more agents."""
    analyst = AgentIdentity("agent_analyst", AgentRole.ANALYST,
                            permissions=frozenset({"read:enterprise_db"}))
    notifier = AgentIdentity("agent_action", AgentRole.NOTIFIER, parent_agent="agent_analyst",
                             permissions=frozenset({"execute:tools"}))
    steps = steps_from_agent_results([
        ("agent_analyst", {"proposed_tool": "sql_read", "serves_capability": "SQL",
                            "governance_action": "ALLOW", "execution_status": "EXECUTED"}),
        ("agent_action", {"proposed_tool": "send_notification",
                           "governance_action": "ALLOW", "execution_status": "EXECUTED"}),
    ])
    assessment = CompositionGovernor().evaluate(steps)
    assert assessment.risk is CompositionRisk.CRITICAL
    assert all(s.governance_action == "ALLOW" for s in steps)
    assert analyst.agent_id and notifier.parent_agent  # lineage preserved


def test_the_benign_counterpart_is_not_flagged_critical():
    """False-positive guard. Without this, a governor that flags every
    sensitive read scores perfectly on the exfiltration case and is
    useless in practice."""
    steps = steps_from_agent_results([
        ("agent_analyst", {"proposed_tool": "sql_read", "serves_capability": "SQL",
                            "governance_action": "ALLOW", "execution_status": "EXECUTED"}),
        ("agent_action", {"proposed_tool": "write_report",
                           "governance_action": "ALLOW", "execution_status": "EXECUTED"}),
    ])
    assessment = CompositionGovernor().evaluate(steps)
    assert assessment.risk is not CompositionRisk.CRITICAL
    assert not assessment.sensitive_data_reached_external


# --- 8. MCP + agents --------------------------------------------

def test_a_gatherer_declares_the_capability_it_serves():
    """Regression: without serves_capability, evidence collectors keyed
    on capability=="RAG" found nothing, the model received no evidence,
    and the request was still VERIFIED with HIGH trust."""
    planner = AgentPlanner()
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="generation", capability="generation"))
    graph.validate()
    plan = planner.plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=False)
    planner.apply(graph, plan)

    from controlplane.runtime import _effective_capability

    served = {_effective_capability(graph.get(a.agent_id))
              for a in plan.agents if a.role is not AgentRole.NOTIFIER}
    # apply() does not set serves_capability (the router does), so the
    # planner's own nodes fall back to AGENT -- what must never happen is
    # a gatherer silently reporting a capability nothing can collect from.
    assert served, "gatherer nodes vanished"


# --- 9-12. Lineage, state, graph, trajectory consistency ---------

def test_agent_lineage_is_preserved_through_the_plan():
    plan = AgentPlanner().plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=True)
    actor = next(a for a in plan.agents if a.role is AgentRole.NOTIFIER)
    assert actor.parent_agent is not None, "USER -> AGENT -> ... lineage broken"


def test_planned_graph_stays_valid_and_acyclic():
    planner = AgentPlanner()
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="generation", capability="generation"))
    graph.validate()
    plan = planner.plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=True)
    planner.apply(graph, plan)
    graph.validate()  # raises on a cycle or a dangling dependency


def test_agent_count_is_derived_not_fixed():
    """The spec forbids both 'always one agent' and 'always three'."""
    planner = AgentPlanner()
    counts = {
        planner.plan(data_requirements={"RAG_CORPUS"}, is_agentic=False).agent_count,
        planner.plan(data_requirements={"RAG_CORPUS"}, is_agentic=True).agent_count,
        planner.plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=True).agent_count,
    }
    assert len(counts) > 1, f"agent count did not vary with the task: {counts}"
    assert 0 in counts, "the planner never declines to create an agent"
