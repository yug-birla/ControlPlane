import pytest

from controlplane.execution.graph import ExecutionGraph, ExecutionNode, GraphError, NodeStatus


def test_ready_nodes_with_no_dependencies():
    graph = ExecutionGraph([ExecutionNode(node_id="a", capability="x"), ExecutionNode(node_id="b", capability="y")])
    ready_ids = {n.node_id for n in graph.ready_nodes()}
    assert ready_ids == {"a", "b"}


def test_dependent_node_not_ready_until_dependency_completes():
    graph = ExecutionGraph([
        ExecutionNode(node_id="a", capability="x"),
        ExecutionNode(node_id="b", capability="y", depends_on=("a",)),
    ])
    assert [n.node_id for n in graph.ready_nodes()] == ["a"]
    graph.get("a").status = NodeStatus.COMPLETED
    assert [n.node_id for n in graph.ready_nodes()] == ["b"]


def test_unknown_dependency_raises_graph_error():
    with pytest.raises(GraphError):
        ExecutionGraph([ExecutionNode(node_id="a", capability="x", depends_on=("missing",))])


def test_cycle_detection():
    with pytest.raises(GraphError):
        ExecutionGraph([
            ExecutionNode(node_id="a", capability="x", depends_on=("b",)),
            ExecutionNode(node_id="b", capability="y", depends_on=("a",)),
        ])


def test_duplicate_node_id_rejected():
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="a", capability="x"))
    with pytest.raises(GraphError):
        graph.add_node(ExecutionNode(node_id="a", capability="y"))


def test_blocked_nodes_when_dependency_failed():
    graph = ExecutionGraph([
        ExecutionNode(node_id="a", capability="x"),
        ExecutionNode(node_id="b", capability="y", depends_on=("a",)),
    ])
    graph.get("a").status = NodeStatus.FAILED
    assert [n.node_id for n in graph.blocked_nodes()] == ["b"]
    assert graph.ready_nodes() == []


def test_is_complete_true_only_when_every_node_is_terminal_or_blocked():
    graph = ExecutionGraph([ExecutionNode(node_id="a", capability="x")])
    assert graph.is_complete() is False
    graph.get("a").status = NodeStatus.COMPLETED
    assert graph.is_complete() is True


def test_critical_path_sums_longest_dependency_chain():
    graph = ExecutionGraph([
        ExecutionNode(node_id="a", capability="x"),
        ExecutionNode(node_id="b", capability="y", depends_on=("a",)),
    ])
    graph.get("a").started_at, graph.get("a").completed_at = 0.0, 0.1  # 100ms
    graph.get("b").started_at, graph.get("b").completed_at = 0.1, 0.35  # 250ms
    assert graph.critical_path_ms() == pytest.approx(350.0)


def test_to_dict_is_json_serializable_and_hides_no_reasoning():
    graph = ExecutionGraph([ExecutionNode(node_id="a", capability="SQL")])
    d = graph.to_dict()
    assert d == {"nodes": [{"node_id": "a", "capability": "SQL", "depends_on": [], "status": "PENDING", "latency_ms": None}]}
