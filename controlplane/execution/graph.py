"""Execution Graph -- represents WHAT SHOULD HAPPEN for one request
(docs/architecture/RUNTIME_FLOW.md SS6.1). Distinct from the Trajectory
Store (what already happened) and the Execution Ledger (consequential
facts) -- see docs/architecture/TRAJECTORY_AND_LEDGER.md.

Deliberately dependency-free (no DB, no event bus) so it can be built,
validated, and unit-tested in isolation. ``controlplane.routing`` builds
graphs from routing decisions; ``controlplane.execution.executor`` runs
them; ``controlplane.runtime`` wires both into the request lifecycle and
persists per-node results as trajectory steps/events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NodeStatus(str, Enum):
    """Reuses the trajectory-step status vocabulary
    (``controlplane.trajectory.store`` uses these same strings) plus the
    two graph-specific values a trajectory step doesn't need
    (``READY``/``BLOCKED``/``SKIPPED``) -- see
    docs/architecture/RUNTIME_FLOW.md SS31 (Partial Execution) for
    ``SKIPPED``'s meaning: a node deliberately not run, not a silent
    failure."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"


_TERMINAL = {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED}


class GraphError(Exception):
    """Raised for a structurally invalid graph (cycle, unknown dependency)
    -- never a runtime execution failure, which belongs on the node."""


@dataclass
class ExecutionNode:
    node_id: str
    capability: str
    """A ``CapabilityHint`` value (or "merge"/"generation" -- see
    controlplane/routing/capability_router.py) identifying which handler
    the executor should invoke. Kept as ``str`` here so the graph module
    has no dependency on the query_intelligence enum."""
    depends_on: tuple[str, ...] = ()
    requires_all_dependencies: bool = True
    """When False, this node becomes ready once every dependency has
    RESOLVED (completed, failed, skipped or blocked) and AT LEAST ONE
    completed.

    This is graceful degradation for fan-in nodes: a ``merge`` that
    demands all of its evidence sources succeed will block generation
    entirely because one capability failed, even when another returned
    perfectly good evidence. Milestone 11 hit exactly that -- RAG
    succeeded, SQL failed, and the whole request died rather than
    answering from the evidence it did have.

    Deliberately opt-in per node rather than a global executor rule: a
    node that genuinely needs every input (a comparison across two
    sources, say) must still block, and silently relaxing that for
    everything would turn a correctness requirement into a race."""
    status: NodeStatus = NodeStatus.PENDING
    input_ref: dict = field(default_factory=dict)
    output_ref: dict = field(default_factory=dict)
    error: str | None = None
    started_at: float | None = None
    """``time.monotonic()`` timestamps -- wall-clock latency measurement,
    never used for ordering (sequence is dependency-derived, not clock-derived)."""
    completed_at: float | None = None

    @property
    def latency_ms(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at) * 1000


class ExecutionGraph:
    """Nodes + dependency edges for one request. Mutable: node statuses
    are updated in place as the ``GraphExecutor`` runs them."""

    def __init__(self, nodes: list[ExecutionNode] | None = None) -> None:
        self._nodes: dict[str, ExecutionNode] = {}
        for node in nodes or []:
            self.add_node(node)
        if nodes:
            self.validate()

    def add_node(self, node: ExecutionNode) -> None:
        if node.node_id in self._nodes:
            raise GraphError(f"duplicate node_id: {node.node_id}")
        self._nodes[node.node_id] = node

    @property
    def nodes(self) -> list[ExecutionNode]:
        return list(self._nodes.values())

    def get(self, node_id: str) -> ExecutionNode:
        return self._nodes[node_id]

    def validate(self) -> None:
        """Raises ``GraphError`` for an unknown dependency or a cycle.
        Called automatically when nodes are supplied at construction;
        callers building a graph incrementally via ``add_node`` should
        call this once before executing."""
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep not in self._nodes:
                    raise GraphError(f"node {node.node_id!r} depends on unknown node {dep!r}")

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node_id: WHITE for node_id in self._nodes}

        def visit(node_id: str, path: list[str]) -> None:
            color[node_id] = GRAY
            for dep in self._nodes[node_id].depends_on:
                if color[dep] == GRAY:
                    cycle = " -> ".join([*path, dep])
                    raise GraphError(f"dependency cycle detected: {cycle}")
                if color[dep] == WHITE:
                    visit(dep, [*path, dep])
            color[node_id] = BLACK

        for node_id in self._nodes:
            if color[node_id] == WHITE:
                visit(node_id, [node_id])

    def ready_nodes(self) -> list[ExecutionNode]:
        """Nodes whose dependencies are all COMPLETED and which are
        themselves still PENDING. A node with a FAILED/SKIPPED dependency
        is never ready -- see ``blocked_nodes``."""
        ready = []
        for node in self._nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps = [self._nodes[d] for d in node.depends_on]
            if node.requires_all_dependencies:
                if all(d.status == NodeStatus.COMPLETED for d in deps):
                    ready.append(node)
            else:
                # Partial-evidence node: ready once nothing is still in
                # flight and at least one dependency produced something.
                resolved = all(
                    d.status in (NodeStatus.COMPLETED, NodeStatus.FAILED,
                                 NodeStatus.SKIPPED, NodeStatus.BLOCKED)
                    for d in deps
                )
                if resolved and any(d.status == NodeStatus.COMPLETED for d in deps):
                    ready.append(node)
        return ready

    def blocked_nodes(self) -> list[ExecutionNode]:
        """PENDING nodes that can never become ready because a dependency
        FAILED or was SKIPPED. The executor marks these BLOCKED rather
        than leaving them PENDING forever (bootstrap SS31: never silently
        strand a step)."""
        blocked = []
        for node in self._nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps = [self._nodes[d] for d in node.depends_on]
            unusable = [d for d in deps
                        if d.status in (NodeStatus.FAILED, NodeStatus.SKIPPED, NodeStatus.BLOCKED)]
            if not unusable:
                continue
            if node.requires_all_dependencies:
                blocked.append(node)
            elif len(unusable) == len(deps):
                # A partial-evidence node is only blocked when EVERY
                # source failed -- with nothing to merge there is nothing
                # to degrade to.
                blocked.append(node)
        return blocked

    def is_complete(self) -> bool:
        return all(n.status in _TERMINAL or n.status == NodeStatus.BLOCKED for n in self._nodes.values())

    def has_failed(self) -> bool:
        return any(n.status == NodeStatus.FAILED for n in self._nodes.values())

    def critical_path_ms(self) -> float | None:
        """Longest dependency-respecting chain of measured latencies --
        the wall-clock lower bound regardless of how much extra work ran
        in parallel (docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md SS54:
        "the router must optimize critical-path latency, not total
        compute time"). Returns None if any node on every path is
        unmeasured (e.g. SKIPPED before starting)."""

        memo: dict[str, float] = {}

        def longest_to(node_id: str) -> float:
            if node_id in memo:
                return memo[node_id]
            node = self._nodes[node_id]
            own = node.latency_ms or 0.0
            if not node.depends_on:
                memo[node_id] = own
            else:
                memo[node_id] = own + max((longest_to(d) for d in node.depends_on), default=0.0)
            return memo[node_id]

        if not self._nodes:
            return None
        return max(longest_to(n) for n in self._nodes)

    def to_dict(self) -> dict:
        """Auditable, hidden-reasoning-free structure for persistence
        (trajectory step output_ref / route_decisions row) -- node ids,
        capabilities, dependencies, and status only."""
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "capability": n.capability,
                    "depends_on": list(n.depends_on),
                    "status": n.status.value,
                    "latency_ms": n.latency_ms,
                    # Agent identity and the capability a gatherer agent
                    # serves. Structured facts only -- no reasoning, no
                    # payloads -- so the dashboard can show WHICH agent did
                    # WHAT without exposing anything it should not.
                    "input_ref": {
                        k: v for k, v in (n.input_ref or {}).items()
                        if k in ("agent_id", "role", "serves_capability")
                    } or None,
                    "error": n.error,
                }
                for n in self._nodes.values()
            ]
        }
