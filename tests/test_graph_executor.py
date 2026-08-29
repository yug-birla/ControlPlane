import time

import pytest

from controlplane.execution.executor import GraphExecutor, mocked_capability_handler
from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus


def test_single_node_runs_via_its_handler():
    graph = ExecutionGraph([ExecutionNode(node_id="a", capability="generation")])
    executor = GraphExecutor(handlers={"generation": lambda node: {"content": "hi"}})
    result = executor.run(graph)
    assert result.completed == ["a"]
    assert result.succeeded is True
    assert graph.get("a").output_ref == {"content": "hi"}


def test_unregistered_capability_falls_back_to_mocked_handler():
    graph = ExecutionGraph([ExecutionNode(node_id="a", capability="RAG")])
    executor = GraphExecutor(handlers={})
    result = executor.run(graph)
    assert result.completed == ["a"]
    assert graph.get("a").output_ref["status"] == "MOCKED"


def test_handler_exception_marks_node_failed_not_crash():
    def boom(node):
        raise ValueError("simulated failure")

    graph = ExecutionGraph([ExecutionNode(node_id="a", capability="generation")])
    executor = GraphExecutor(handlers={"generation": boom})
    result = executor.run(graph)
    assert result.failed == ["a"]
    assert graph.get("a").error == "simulated failure"
    assert result.succeeded is False


def test_dependent_chain_respects_order():
    call_order = []

    def make(name):
        def handler(node):
            call_order.append(name)
            return {}
        return handler

    graph = ExecutionGraph([
        ExecutionNode(node_id="a", capability="a"),
        ExecutionNode(node_id="b", capability="b", depends_on=("a",)),
    ])
    executor = GraphExecutor(handlers={"a": make("a"), "b": make("b")})
    result = executor.run(graph, mode="sequential")
    assert call_order == ["a", "b"]
    assert result.succeeded is True


def test_failed_dependency_blocks_downstream_node():
    def boom(node):
        raise RuntimeError("fail")

    graph = ExecutionGraph([
        ExecutionNode(node_id="a", capability="a"),
        ExecutionNode(node_id="b", capability="b", depends_on=("a",)),
    ])
    executor = GraphExecutor(handlers={"a": boom, "b": mocked_capability_handler})
    result = executor.run(graph)
    assert result.failed == ["a"]
    assert result.blocked == ["b"]
    assert graph.get("b").status == NodeStatus.BLOCKED


def test_parallel_mode_runs_independent_nodes_concurrently_and_is_faster():
    def slow(node):
        time.sleep(0.15)
        return {}

    def make_graph():
        return ExecutionGraph([
            ExecutionNode(node_id="x", capability="slow"),
            ExecutionNode(node_id="y", capability="slow"),
        ])

    executor = GraphExecutor(handlers={"slow": slow}, max_workers=4)

    sequential_result = executor.run(make_graph(), mode="sequential")
    parallel_result = executor.run(make_graph(), mode="parallel")

    assert sequential_result.succeeded and parallel_result.succeeded
    # Two 150ms nodes: sequential should take ~300ms, parallel ~150ms.
    # Generous margin to avoid CI flakiness -- this is a real, measured
    # timing property, not an exact-value assertion.
    assert parallel_result.total_latency_ms < sequential_result.total_latency_ms * 0.75


def test_blocking_propagates_transitively_through_a_dependency_chain_regression():
    """Regression (Milestone 11): blocking was propagated only ONE level
    per loop iteration. With data -> merge -> generation, marking `merge`
    BLOCKED left `generation` PENDING, so ready_nodes() came back empty
    while the graph was not yet complete -- and the executor raised
    GraphError on an ordinary capability failure.

    Any failure with two or more levels of dependents hit this. Surfaced
    by a deliberately failing MCP capability."""
    from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus

    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="data_sql", capability="SQL"))
    graph.add_node(ExecutionNode(node_id="merge", capability="merge", depends_on=("data_sql",)))
    graph.add_node(ExecutionNode(node_id="generation", capability="generation", depends_on=("merge",)))
    graph.validate()

    def _boom(node):
        raise RuntimeError("capability exploded")

    executor = GraphExecutor(handlers={"SQL": _boom})
    result = executor.run(graph)  # must not raise

    assert "data_sql" in result.failed
    assert set(result.blocked) == {"merge", "generation"}
    assert graph.get("generation").status is NodeStatus.BLOCKED


def test_a_deep_chain_of_dependents_all_become_blocked():
    """Fixed-point propagation must handle more than two levels."""
    from controlplane.execution.graph import ExecutionGraph, ExecutionNode

    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="a", capability="SQL"))
    previous = "a"
    for name in ("b", "c", "d", "e"):
        graph.add_node(ExecutionNode(node_id=name, capability="generation", depends_on=(previous,)))
        previous = name
    graph.validate()

    def _boom(node):
        raise RuntimeError("boom")

    result = GraphExecutor(handlers={"SQL": _boom}).run(graph)
    assert set(result.blocked) == {"b", "c", "d", "e"}


def test_merge_proceeds_on_partial_evidence_when_one_source_fails():
    """Graceful degradation (Milestone 11): RAG succeeded and SQL failed.
    Answering from the evidence that DID arrive is correct; blocking
    generation entirely because one source failed is not.

    Found the hard way -- a failing MCP capability blocked merge, which
    blocked generation, and the runtime then crashed with KeyError
    because no result was ever produced."""
    from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus

    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="data_rag", capability="RAG"))
    graph.add_node(ExecutionNode(node_id="data_sql", capability="SQL"))
    graph.add_node(ExecutionNode(
        node_id="merge", capability="merge",
        depends_on=("data_rag", "data_sql"), requires_all_dependencies=False,
    ))
    graph.add_node(ExecutionNode(node_id="generation", capability="generation", depends_on=("merge",)))
    graph.validate()

    def _sql_boom(node):
        raise RuntimeError("sql exploded")

    executor = GraphExecutor(handlers={
        "RAG": lambda node: {"chunks": [{"text": "Meals are $75/day."}]},
        "SQL": _sql_boom,
        "merge": lambda node: {"merged": True},
        "generation": lambda node: {"content": "The limit is $75/day."},
    })
    result = executor.run(graph)

    assert "data_sql" in result.failed
    assert "data_rag" in result.completed
    # The key property: generation still ran on the surviving evidence.
    assert "generation" in result.completed
    assert graph.get("merge").status is NodeStatus.COMPLETED


def test_merge_is_blocked_only_when_every_evidence_source_fails():
    """With nothing to merge there is nothing to degrade to -- that must
    block rather than fabricate an answer from no evidence."""
    from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus

    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="data_rag", capability="RAG"))
    graph.add_node(ExecutionNode(node_id="data_sql", capability="SQL"))
    graph.add_node(ExecutionNode(
        node_id="merge", capability="merge",
        depends_on=("data_rag", "data_sql"), requires_all_dependencies=False,
    ))
    graph.add_node(ExecutionNode(node_id="generation", capability="generation", depends_on=("merge",)))
    graph.validate()

    def _boom(node):
        raise RuntimeError("boom")

    result = GraphExecutor(handlers={"RAG": _boom, "SQL": _boom}).run(graph)
    assert set(result.blocked) == {"merge", "generation"}
    assert graph.get("generation").status is NodeStatus.BLOCKED


def test_a_node_requiring_all_dependencies_still_blocks_on_one_failure():
    """The relaxation must be opt-in: a node that genuinely needs every
    input (a cross-source comparison, say) must still block."""
    from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus

    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="a", capability="RAG"))
    graph.add_node(ExecutionNode(node_id="b", capability="SQL"))
    graph.add_node(ExecutionNode(node_id="compare", capability="generation", depends_on=("a", "b")))
    graph.validate()

    def _boom(node):
        raise RuntimeError("boom")

    result = GraphExecutor(handlers={"RAG": lambda n: {"ok": True}, "SQL": _boom}).run(graph)
    assert "compare" in result.blocked
    assert graph.get("compare").status is NodeStatus.BLOCKED
