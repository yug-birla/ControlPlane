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
from controlplane.governance.multi_agent import AgentRole
from controlplane.planning.agent_planner import AgentPlanner
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

    def __init__(self, agent_planner: AgentPlanner | None = None) -> None:
        # Multi-agent planning (Milestone 12). Injected so a test can
        # supply a planner without this router importing a registry.
        self._agent_planner = agent_planner or AgentPlanner()

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

        # MULTI-AGENT PLANNING (Milestone 12). The planner decides how many
        # agents the task actually justifies, from the query's own measured
        # data requirements -- rather than this router always emitting
        # exactly one agent node.
        #
        # It is consulted only when the query is agentic or genuinely needs
        # several independent data sources; for everything else it returns
        # an empty plan and the single-node path below is used unchanged.
        # That is the planner's own rule ("a plain capability path does this
        # work without agent overhead"), not a special case here.
        agent_plan = None
        if agent_selected or len(data_caps) > 1:
            agent_plan = self._agent_planner.plan(
                data_requirements=set(fingerprint.data_requirement or []),
                is_agentic=agent_selected,
                restricted_capabilities=set(policy.restricted_capabilities),
            )

        if agent_plan is not None and agent_plan.agent_count > 0:
            self._agent_planner.apply(graph, agent_plan)
            # The actor must not act before the answer it may act on
            # exists. Found by ROLE rather than by a hardcoded node id, so
            # renaming a node cannot silently drop this dependency.
            actor = next((a for a in agent_plan.agents if a.role is AgentRole.NOTIFIER), None)
            if actor is not None:
                node = graph.get(actor.agent_id)
                node.depends_on = tuple(sorted(set(node.depends_on) | {"generation"}))
        elif agent_selected:
            graph.add_node(ExecutionNode(
                node_id="agent_action", capability=CapabilityHint.AGENT.value,
                depends_on=("generation",),
            ))
        graph.validate()

        reason_parts = [f"capability_hints={sorted(candidate)}"]
        if restricted:
            reason_parts.append(f"restricted_by_policy(tier={policy.tier.value})={restricted}")
        reason_parts.append(f"selected={sorted(selected)}")
        if agent_plan is not None and agent_plan.agent_count:
            reason_parts.append(f"agent_plan={agent_plan.reason}")

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
