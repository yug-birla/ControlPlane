"""Multi-agent planning: use the minimum number of agents the task justifies.

The spec is explicit -- "do not always use one agent, do not always use
three agents" -- so these tests pin down that the count is DERIVED, and
in particular that the planner declines to create agents when a plain
capability path would do the same work.
"""

from __future__ import annotations

from controlplane.execution.graph import ExecutionGraph, ExecutionNode
from controlplane.governance.multi_agent import AgentRole
from controlplane.planning.agent_planner import AgentPlanner


def _graph() -> ExecutionGraph:
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="generation", capability="generation"))
    graph.validate()
    return graph


def test_a_single_data_source_and_no_action_justifies_no_agents():
    """A plain capability node does this work without the governance
    overhead of an identity, permissions, and a gated proposal. Creating
    an agent here would be theatre."""
    plan = AgentPlanner().plan(data_requirements={"RAG_CORPUS"}, is_agentic=False)
    assert plan.agent_count == 0
    assert "without agent overhead" in plan.reason


def test_two_independent_data_sources_justify_two_agents_in_parallel():
    plan = AgentPlanner().plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=False)
    assert plan.agent_count == 2
    assert {a.role for a in plan.agents} == {AgentRole.RETRIEVER, AgentRole.ANALYST}
    assert len(plan.parallel_groups) == 1
    assert len(plan.parallel_groups[0]) == 2


def test_an_action_request_justifies_an_actor_agent():
    plan = AgentPlanner().plan(data_requirements={"RAG_CORPUS"}, is_agentic=True)
    assert plan.agent_count == 1
    assert plan.agents[0].role is AgentRole.NOTIFIER
    # Established id preserved -- see the planner's comment.
    assert plan.agents[0].agent_id == "agent_action"


def test_data_plus_action_produces_gatherers_and_a_dependent_actor():
    plan = AgentPlanner().plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=True)
    assert plan.agent_count == 3
    actor = plan.agents[-1]
    assert actor.role is AgentRole.NOTIFIER
    # The actor must not act before the evidence it acts on has arrived.
    assert actor.parent_agent is not None


def test_policy_restricted_capabilities_do_not_get_an_agent():
    plan = AgentPlanner().plan(
        data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=False,
        restricted_capabilities={"SQL"},
    )
    assert plan.agent_count == 0  # only one gatherer survives, which does not justify agents


def test_mocked_capabilities_never_get_an_agent():
    """Planning an agent around a placeholder capability produces a plan
    that cannot supply what it promises."""
    plan = AgentPlanner().plan(
        data_requirements={"CHAT_DATABASE", "MEMORY_STORE"}, is_agentic=False
    )
    assert plan.agent_count == 0


def test_applying_the_plan_adds_nodes_with_no_inter_gatherer_dependencies():
    """Parallelism must be a property of the DEPENDENCY STRUCTURE, not a
    flag the planner sets and hopes something honours."""
    planner = AgentPlanner()
    graph = _graph()
    plan = planner.plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=False)
    added = planner.apply(graph, plan)

    assert len(added) == 2
    for node_id in added:
        assert graph.get(node_id).depends_on == (), "gatherers must be independent to run in parallel"
    graph.validate()


def test_the_actor_node_depends_on_every_gatherer():
    planner = AgentPlanner()
    graph = _graph()
    plan = planner.plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=True)
    planner.apply(graph, plan)

    # The actor keeps the established node id: the dashboard's Permission
    # Lineage panel keys on "route:agent_action".
    actor = graph.get("agent_action")
    assert set(actor.depends_on) == {"agent_retriever", "agent_analyst"}
    # But it should still act on partial evidence rather than be blocked
    # entirely by one failed gatherer.
    assert actor.requires_all_dependencies is False


def test_applying_twice_does_not_duplicate_nodes():
    planner = AgentPlanner()
    graph = _graph()
    plan = planner.plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=False)
    planner.apply(graph, plan)
    second = planner.apply(graph, plan)
    assert second == []
    assert len([n for n in graph.nodes if n.node_id == "agent_retriever"]) == 1


def test_planned_agents_carry_distinct_permissions_for_composition_governance():
    """CompositionGovernor reasons about accumulated authority across a
    chain; identical permission sets would make that meaningless."""
    plan = AgentPlanner().plan(data_requirements={"RAG_CORPUS", "SQL_DB"}, is_agentic=True)
    permission_sets = [a.permissions for a in plan.agents]
    assert len(set(permission_sets)) == len(permission_sets)
