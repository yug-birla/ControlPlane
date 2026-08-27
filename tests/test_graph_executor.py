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
