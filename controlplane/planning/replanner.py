"""Dynamic replanning that actually changes the execution graph.

THE PROBLEM (Milestone 10 §6/§38, stated there as "the most important
current architectural problem"):

Through Milestone 9, a "replan" bumped ``plan_version``, emitted
``REPLAN_TRIGGERED``, and re-ran the *existing* RAG node with a wider
``k``. The execution graph itself never changed -- no node was ever
added, removed, or replaced. The system recorded plan versions while
executing a fixed workflow, which is precisely what §38 warns against:
"Do not keep one fixed graph while pretending planning is dynamic."

WHAT THIS ADDS: on insufficient evidence, ControlPlane consults the
Capability Registry for a DIFFERENT capability that could supply the
evidence the query still needs, and ADDS it to the graph as a new node
with the merge node rewired to depend on it. That produces a genuinely
different PLAN V2.

NOT HARD-CODED (§46 is explicit: "Do NOT hard-code: RAG FAILURE ->
ALWAYS SQL"). The alternative capability is selected by matching the
query's own measured ``data_requirement`` values against registry
metadata, filtered by policy restrictions, by what has already been
tried, and by whether the capability is actually usable. A query with no
unserved data requirement gets no new node -- and the system correctly
falls back to widening retrieval rather than inventing a capability that
cannot help.

PLAN VERSIONING (§10): the previous plan is never overwritten. Each
replan records old version, trigger, decision, the specific nodes added,
and the new version.

AUTHORITY: this module proposes a graph change. It does not decide
whether to replan -- the Decision Engine does that -- and it never
executes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from controlplane.capabilities.registry import (
    CapabilityDescriptor,
    CapabilityRegistry,
    get_capability_registry,
)
from controlplane.execution.graph import ExecutionGraph, ExecutionNode

_MERGE_NODE_ID = "merge"
_GENERATION_NODE_ID = "generation"


@dataclass
class PlanChange:
    """A proposed, not-yet-applied mutation of the execution graph."""

    changed: bool
    added_nodes: list[str] = field(default_factory=list)
    added_capabilities: list[str] = field(default_factory=list)
    reason: str = ""
    rejected_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "changed": self.changed,
            "added_nodes": self.added_nodes,
            "added_capabilities": self.added_capabilities,
            "reason": self.reason,
            "rejected_reason": self.rejected_reason,
        }


class Replanner:
    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry or get_capability_registry()

    def propose_additional_evidence_capability(
        self,
        *,
        graph: ExecutionGraph,
        data_requirements: set[str],
        restricted_capabilities: set[str],
    ) -> tuple[PlanChange, CapabilityDescriptor | None]:
        """Find a capability that could serve an as-yet-unserved data
        requirement of THIS query, and is not already in the graph.

        Returns the proposal and the descriptor, without mutating
        anything -- applying it is a separate, explicit step so a caller
        can record PLAN V1 before PLAN V2 exists.
        """
        present = {n.capability for n in graph.nodes}

        if not data_requirements:
            return (
                PlanChange(
                    changed=False,
                    rejected_reason="the query has no declared data requirement, so no "
                                    "additional evidence capability could be justified",
                ),
                None,
            )

        # Which of this query's data requirements is nothing in the graph
        # already serving? That is the actual gap to fill.
        unserved = set(data_requirements)
        for capability_id in present:
            descriptor = self._registry.get(capability_id)
            if descriptor:
                unserved -= descriptor.satisfies_data_requirements

        if not unserved:
            return (
                PlanChange(
                    changed=False,
                    rejected_reason=f"every declared data requirement {sorted(data_requirements)} "
                                    "is already served by a node in the current plan",
                ),
                None,
            )

        candidates = self._registry.discover(
            data_requirements=unserved,
            supplies_evidence=True,
            exclude=present,
            restricted=restricted_capabilities,
        )
        if not candidates:
            return (
                PlanChange(
                    changed=False,
                    rejected_reason=f"no available, policy-permitted capability serves {sorted(unserved)} "
                                    "(candidates may exist but be MOCKED, unavailable, or restricted)",
                ),
                None,
            )

        chosen = candidates[0]
        return (
            PlanChange(
                changed=True,
                added_capabilities=[chosen.capability_id],
                reason=(
                    f"evidence was insufficient and data requirement(s) {sorted(unserved)} "
                    f"were unserved by the current plan; {chosen.capability_id} "
                    f"({chosen.name}) satisfies them and is AVAILABLE, read-permitted, "
                    f"cost={chosen.cost_class}"
                ),
            ),
            chosen,
        )

    def apply(self, graph: ExecutionGraph, descriptor: CapabilityDescriptor) -> PlanChange:
        """Mutate the graph: add the capability node and rewire the merge
        node to depend on it, so its evidence actually reaches generation.

        Adding a node whose output nothing consumes would be theatre --
        the plan would look different while the prompt stayed identical.
        """
        node_id = f"data_{descriptor.capability_id.lower()}"
        if any(n.node_id == node_id for n in graph.nodes):
            return PlanChange(changed=False, rejected_reason=f"node {node_id} already exists")

        graph.add_node(ExecutionNode(node_id=node_id, capability=descriptor.capability_id))

        merge = next((n for n in graph.nodes if n.node_id == _MERGE_NODE_ID), None)
        if merge is not None:
            merge.depends_on = tuple(sorted(set(merge.depends_on) | {node_id}))
        else:
            # A plan that had no data capabilities at all has no merge
            # node; introduce one so generation consumes the new evidence.
            generation = next((n for n in graph.nodes if n.node_id == _GENERATION_NODE_ID), None)
            graph.add_node(ExecutionNode(node_id=_MERGE_NODE_ID, capability="merge", depends_on=(node_id,)))
            if generation is not None:
                generation.depends_on = tuple(sorted(set(generation.depends_on) | {_MERGE_NODE_ID}))

        graph.validate()  # cycles/dangling deps must fail loudly, not at execution time
        return PlanChange(
            changed=True,
            added_nodes=[node_id],
            added_capabilities=[descriptor.capability_id],
            reason=f"added {descriptor.capability_id} node {node_id!r} and rewired merge to consume it",
        )
