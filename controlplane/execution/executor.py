"""Graph Executor -- runs an ``ExecutionGraph`` respecting dependency
order, optionally running each wave of ready nodes concurrently
(bootstrap Rule 8: bounded concurrency, not unbounded fan-out).

A "wave" is one batch of nodes that became ready at the same time (all
their dependencies just completed). Waves run strictly in order; nodes
within a wave run in parallel (mode="parallel") or one at a time
(mode="sequential") -- the same graph, executed both ways, is exactly
the sequential-vs-parallel benchmark required by
docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md SS54 /
controlplane/experiments/benchmark_graph_execution.py.

A capability with no registered handler is not silently skipped or
faked as success -- it runs the explicit ``mocked_capability_handler``,
which returns a result tagged ``status: "MOCKED"`` (bootstrap SS54: never
report NOT_IMPLEMENTED work as IMPLEMENTED).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from controlplane.execution.graph import ExecutionGraph, ExecutionNode, GraphError, NodeStatus

NodeHandler = Callable[[ExecutionNode], dict]


def mocked_capability_handler(node: ExecutionNode) -> dict:
    """Default handler for any capability that has no real implementation
    yet (SQL/RAG/WEB/CHAT_HISTORY/MEMORY/AGENT -- Layer 5/11/18 not
    started, see docs/PROJECT_STATE/FUTURE_WORK.md). Returns a clearly
    labeled placeholder, never fabricated content."""
    return {
        "status": "MOCKED",
        "note": f"capability {node.capability!r} has no real implementation yet (see docs/PROJECT_STATE/FUTURE_WORK.md)",
    }


@dataclass
class GraphResult:
    graph: ExecutionGraph
    total_latency_ms: float
    critical_path_ms: float | None
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    mode: str = "parallel"

    @property
    def succeeded(self) -> bool:
        return not self.failed and not self.blocked


class GraphExecutor:
    def __init__(self, handlers: dict[str, NodeHandler], max_workers: int = 4) -> None:
        self._handlers = handlers
        self._max_workers = max_workers

    def _handler_for(self, capability: str) -> NodeHandler:
        return self._handlers.get(capability, mocked_capability_handler)

    def _run_node(self, node: ExecutionNode) -> None:
        node.status = NodeStatus.RUNNING
        node.started_at = time.monotonic()
        try:
            node.output_ref = self._handler_for(node.capability)(node)
            node.status = NodeStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001 -- a node failure must never crash the executor
            node.error = str(exc)
            node.status = NodeStatus.FAILED
        finally:
            node.completed_at = time.monotonic()

    def run(self, graph: ExecutionGraph, mode: str = "parallel") -> GraphResult:
        if mode not in ("parallel", "sequential"):
            raise ValueError(f"unknown mode: {mode!r}")
        graph.validate()

        wall_start = time.monotonic()
        while not graph.is_complete():
            for node in graph.blocked_nodes():
                node.status = NodeStatus.BLOCKED

            wave = graph.ready_nodes()
            if not wave:
                if graph.is_complete():
                    break
                raise GraphError("no ready nodes but graph is not complete -- this indicates a bug, not user error")

            if mode == "sequential" or len(wave) == 1:
                for node in wave:
                    self._run_node(node)
            else:
                with ThreadPoolExecutor(max_workers=min(self._max_workers, len(wave))) as pool:
                    list(pool.map(self._run_node, wave))

        wall_ms = (time.monotonic() - wall_start) * 1000
        return GraphResult(
            graph=graph,
            total_latency_ms=wall_ms,
            critical_path_ms=graph.critical_path_ms(),
            completed=[n.node_id for n in graph.nodes if n.status == NodeStatus.COMPLETED],
            failed=[n.node_id for n in graph.nodes if n.status == NodeStatus.FAILED],
            blocked=[n.node_id for n in graph.nodes if n.status == NodeStatus.BLOCKED],
            mode=mode,
        )
