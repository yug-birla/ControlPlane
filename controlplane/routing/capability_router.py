"""Capability Router -- V0 per docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md
SS14 ("rules + taxonomy"). Answers: what capabilities does this query
need, and in what order/parallel structure should they run?

Deliberately reuses ``QueryFingerprint.capability_hints`` (already
produced by the Query Profiler, docs/EVALUATION/QUERY_PROFILER_RESULTS.md)
rather than re-classifying the query -- the routing spec explicitly warns
against a second independent classification call (SS3: "ONE cheap
query-intelligence inference ... should be sufficient for most
requests"). This router's own job is policy filtering and turning a set
of capabilities into an ``ExecutionGraph`` (dependency structure), not
re-deriving what the query needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from controlplane.execution.graph import ExecutionGraph, ExecutionNode
from controlplane.policy.baseline import PolicyDecision
from controlplane.query_intelligence.fingerprint import CapabilityHint, QueryFingerprint
from controlplane.risk.profile import RiskProfile

# Capabilities that fetch/retrieve data and can therefore run in
# parallel with each other (no dependency between them) before anything
# that needs their combined output. None of these have a real capability
# implementation yet (Layer 5/11/18 -- see docs/PROJECT_STATE/FUTURE_WORK.md);
# the executor runs them via the explicit MOCKED handler.
_DATA_CAPABILITIES = {
    CapabilityHint.SQL.value,
    CapabilityHint.RAG.value,
    CapabilityHint.WEB.value,
    CapabilityHint.CHAT_HISTORY.value,
    CapabilityHint.MEMORY.value,
}

# Capabilities that are satisfied by a single model generation call
# (the only capability this milestone actually implements for real).
_GENERATION_CAPABILITIES = {
    CapabilityHint.GENERAL.value,
    CapabilityHint.REASONING.value,
    CapabilityHint.CODING.value,
}


@dataclass
class CapabilityRoute:
    selected_capabilities: list[str]
    """Post-restriction capability set actually routed to (never empty --
    floors to [GENERAL] per docs/PROJECT_STATE/DECISIONS.md, same floor
    rule the Query Profiler already uses)."""
    restricted_removed: list[str]
    """Capabilities the fingerprint suggested but policy blocked at this
    risk tier -- always reported, never silently dropped."""
    graph: ExecutionGraph
    reason: str
    expected_cost_class: str
    """"LOW"/"MEDIUM"/"HIGH" -- an ESTIMATE from node count/type, not a
    measured cost (docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md SS53:
    never present an estimate as a measurement)."""
    expected_latency_class: str

    def to_dict(self) -> dict:
        return {
            "selected_capabilities": self.selected_capabilities,
            "restricted_removed": self.restricted_removed,
            "reason": self.reason,
            "expected_cost_class": self.expected_cost_class,
            "expected_latency_class": self.expected_latency_class,
            "graph": self.graph.to_dict(),
        }


class CapabilityRouter:
    name = "rules_v0"

    def route(self, fingerprint: QueryFingerprint, risk: RiskProfile, policy: PolicyDecision) -> CapabilityRoute:
        candidate = {h.value for h in fingerprint.capability_hints} - {CapabilityHint.MULTI_SOURCE.value}
        restricted = sorted(candidate & set(policy.restricted_capabilities))
        selected = candidate - set(policy.restricted_capabilities)
        if not selected:
            selected = {CapabilityHint.GENERAL.value}

        data_caps = sorted(selected & _DATA_CAPABILITIES)
        agent_selected = CapabilityHint.AGENT.value in selected

        graph = ExecutionGraph()
        if data_caps:
            for cap in data_caps:
                graph.add_node(ExecutionNode(node_id=f"data_{cap.lower()}", capability=cap))
            graph.add_node(ExecutionNode(
                node_id="merge", capability="merge",
                depends_on=tuple(f"data_{c.lower()}" for c in data_caps),
                # Answer from whatever evidence arrived. One failing
                # source must not block generation when another
                # returned good evidence (graceful degradation).
                requires_all_dependencies=False,
            ))
            graph.add_node(ExecutionNode(node_id="generation", capability="generation", depends_on=("merge",)))
        else:
            graph.add_node(ExecutionNode(node_id="generation", capability="generation"))

        if agent_selected:
            graph.add_node(ExecutionNode(node_id="agent_action", capability=CapabilityHint.AGENT.value, depends_on=("generation",)))
        graph.validate()

        reason_parts = [f"capability_hints={sorted(candidate)}"]
        if restricted:
            reason_parts.append(f"restricted_by_policy(tier={policy.tier.value})={restricted}")
        reason_parts.append(f"selected={sorted(selected)}")

        node_count = len(graph.nodes)
        expected_cost_class = "HIGH" if agent_selected or node_count > 3 else ("MEDIUM" if data_caps else "LOW")
        expected_latency_class = "HIGH" if data_caps and agent_selected else ("MEDIUM" if data_caps or agent_selected else "LOW")

        return CapabilityRoute(
            selected_capabilities=sorted(selected),
            restricted_removed=restricted,
            graph=graph,
            reason=" | ".join(reason_parts),
            expected_cost_class=expected_cost_class,
            expected_latency_class=expected_latency_class,
        )
