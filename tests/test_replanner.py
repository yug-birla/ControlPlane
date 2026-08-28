"""Dynamic replanning: the plan must actually change.

Through Milestone 9 a "replan" bumped plan_version and re-ran the same
node with a bigger k -- the graph never changed. These tests pin down
that a replan now adds a real capability node, that the choice is
DERIVED from the query's data requirements rather than hard-coded, and
that it declines cleanly when no capability could help.
"""

from __future__ import annotations

from controlplane.capabilities.registry import CapabilityRegistry, CapabilityStatus
from controlplane.execution.graph import ExecutionGraph, ExecutionNode
from controlplane.planning.replanner import Replanner


def _rag_only_graph() -> ExecutionGraph:
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="data_rag", capability="RAG"))
    graph.add_node(ExecutionNode(node_id="merge", capability="merge", depends_on=("data_rag",)))
    graph.add_node(ExecutionNode(node_id="generation", capability="generation", depends_on=("merge",)))
    graph.validate()
    return graph


def test_replan_adds_a_capability_that_serves_an_unserved_data_requirement():
    graph = _rag_only_graph()
    change, descriptor = Replanner().propose_additional_evidence_capability(
        graph=graph,
        data_requirements={"RAG_CORPUS", "SQL_DB"},
        restricted_capabilities=set(),
    )
    assert change.changed
    assert descriptor is not None and descriptor.capability_id == "SQL"
    assert "SQL_DB" in change.reason


def test_applying_the_change_adds_the_node_and_rewires_merge():
    """Adding a node whose output nothing consumes would be theatre --
    the plan would look different while the prompt stayed identical."""
    graph = _rag_only_graph()
    replanner = Replanner()
    _change, descriptor = replanner.propose_additional_evidence_capability(
        graph=graph, data_requirements={"RAG_CORPUS", "SQL_DB"}, restricted_capabilities=set()
    )
    applied = replanner.apply(graph, descriptor)

    assert applied.changed
    assert "data_sql" in [n.node_id for n in graph.nodes]
    merge = graph.get("merge")
    assert "data_sql" in merge.depends_on, "new evidence node must feed the merge node"
    graph.validate()


def test_selection_is_driven_by_data_requirements_not_a_hardcoded_rag_to_sql_rule():
    """The same 'RAG produced insufficient evidence' situation must NOT
    pull in SQL when the query never needed structured data. §46 is
    explicit that 'RAG failure -> always SQL' is forbidden."""
    change, descriptor = Replanner().propose_additional_evidence_capability(
        graph=_rag_only_graph(),
        data_requirements={"RAG_CORPUS"},  # no SQL_DB requirement
        restricted_capabilities=set(),
    )
    assert not change.changed
    assert descriptor is None
    assert "already served" in (change.rejected_reason or "")


def test_policy_restricted_capability_is_never_proposed():
    change, descriptor = Replanner().propose_additional_evidence_capability(
        graph=_rag_only_graph(),
        data_requirements={"RAG_CORPUS", "SQL_DB"},
        restricted_capabilities={"SQL"},
    )
    assert not change.changed
    assert descriptor is None


def test_mocked_capabilities_are_not_proposed_as_evidence_sources():
    """CHAT_HISTORY/MEMORY/WEB run via a placeholder handler. Proposing
    one would produce a plan change that cannot supply real evidence."""
    change, descriptor = Replanner().propose_additional_evidence_capability(
        graph=_rag_only_graph(),
        data_requirements={"RAG_CORPUS", "CHAT_DATABASE"},
        restricted_capabilities=set(),
    )
    assert not change.changed
    assert descriptor is None
    assert "MOCKED" in (change.rejected_reason or "")


def test_query_with_no_data_requirements_gets_no_new_capability():
    change, descriptor = Replanner().propose_additional_evidence_capability(
        graph=_rag_only_graph(), data_requirements=set(), restricted_capabilities=set()
    )
    assert not change.changed
    assert descriptor is None


def test_a_plan_with_no_merge_node_gains_one_so_evidence_reaches_generation():
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="generation", capability="generation"))
    graph.validate()

    replanner = Replanner()
    _change, descriptor = replanner.propose_additional_evidence_capability(
        graph=graph, data_requirements={"SQL_DB"}, restricted_capabilities=set()
    )
    assert descriptor is not None
    replanner.apply(graph, descriptor)

    node_ids = [n.node_id for n in graph.nodes]
    assert "data_sql" in node_ids and "merge" in node_ids
    assert "merge" in graph.get("generation").depends_on
    graph.validate()


def test_applying_twice_is_rejected_rather_than_duplicating_a_node():
    graph = _rag_only_graph()
    replanner = Replanner()
    _c, descriptor = replanner.propose_additional_evidence_capability(
        graph=graph, data_requirements={"RAG_CORPUS", "SQL_DB"}, restricted_capabilities=set()
    )
    replanner.apply(graph, descriptor)
    second = replanner.apply(graph, descriptor)
    assert not second.changed
    assert len([n for n in graph.nodes if n.node_id == "data_sql"]) == 1


def test_registry_discovery_prefers_cheaper_capabilities():
    registry = CapabilityRegistry()
    found = registry.discover(data_requirements={"SQL_DB", "RAG_CORPUS"}, supplies_evidence=True)
    assert [d.capability_id for d in found][0] == "SQL"  # LOW cost before RAG's LOW/MEDIUM


def test_registry_status_is_never_more_optimistic_than_reality():
    """A registry that claims a placeholder capability works would make
    the planner choose it and then silently produce no evidence."""
    registry = CapabilityRegistry()
    for capability_id in ("CHAT_HISTORY", "MEMORY", "WEB"):
        assert registry.get(capability_id).status is CapabilityStatus.MOCKED
    for capability_id in ("RAG", "SQL", "AGENT"):
        assert registry.get(capability_id).status is CapabilityStatus.AVAILABLE
