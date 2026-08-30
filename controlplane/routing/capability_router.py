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


# Which real capability each gatherer agent role executes. A gatherer
# agent is a governed wrapper around a capability, not a second
# implementation of it.
_ROLE_CAPABILITY = {
    AgentRole.RETRIEVER: CapabilityHint.RAG.value,
    AgentRole.ANALYST: CapabilityHint.SQL.value,
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

        # MULTI-AGENT PLANNING (Milestone 12). The planner decides how many
        # agents the task actually justifies, from the query's own measured
        # data requirements -- rather than this router always emitting
        # exactly one agent node.
        #
        # THE PLANNER IS ALWAYS CONSULTED, AND is_agentic IS TRUTHFUL.
        #
        # It used to be consulted only when CapabilityHint.AGENT was
        # selected, with is_agentic hard-coded to True. The stated reason
        # was that "agents exist to be governed, so a pure read buys
        # nothing". That argument is about governance only, and it
        # silently decided a question that belongs to the planner.
        #
        # The cost was measured, not theorised. AgentPlanner has an
        # explicit branch for two independent gatherers on a NON-agentic
        # task, covered by six unit tests including
        # ``test_two_independent_data_sources_justify_two_agents_in_parallel``.
        # Because this gate never passed is_agentic=False, that branch was
        # unreachable in production: every one of those tests exercised an
        # input the runtime could not generate. In the multi-agent
        # benchmark, six of the eight cases that expect agents ran with
        # ZERO agents (MA-001/004/005/008/010/012), each carrying both
        # RAG_CORPUS and SQL_DB. Plan-shape accuracy was 0.417, and the
        # four ablation conditions were the same execution path on nine of
        # twelve cases -- which is why they returned identical quality.
        #
        # Deciding whether agents are justified is the planner's whole
        # job, and it already returns zero agents when they are not: a
        # lone servable source with no action still yields an empty plan.
        # Whether decomposing a two-source READ actually pays is now an
        # empirical question the ablation can answer, rather than an
        # assumption baked into a gate.
        agent_plan = self._agent_planner.plan(
            data_requirements=set(fingerprint.data_requirement or []),
            is_agentic=agent_selected,
            restricted_capabilities=set(policy.restricted_capabilities),
            selected_capabilities=selected,
        )
        gatherers = (
            [a for a in agent_plan.agents if a.role is not AgentRole.NOTIFIER]
            if agent_plan else []
        )

        graph = ExecutionGraph()
        if gatherers:
            # Gatherer agents REPLACE the plain data nodes rather than
            # sitting alongside them. Adding both would fetch the same
            # evidence twice -- wasted work, and two provenance trails for
            # one piece of evidence. Each agent node carries the capability
            # it serves, so the executor runs the real RAG/SQL capability
            # under an agent identity that AgentGate and CompositionGovernor
            # can reason about.
            for agent in gatherers:
                graph.add_node(ExecutionNode(
                    node_id=agent.agent_id, capability=CapabilityHint.AGENT.value,
                    input_ref={
                        "agent_id": agent.agent_id, "role": agent.role.value,
                        "serves_capability": _ROLE_CAPABILITY[agent.role],
                    },
                ))
            # ...but only the capabilities a gatherer actually SERVES.
            # Gatherers cover RAG and SQL; a query that also wants WEB or
            # CHAT_HISTORY still needs those plain nodes. Dropping every
            # data node whenever any gatherer existed lost evidence
            # sources silently, and made the multi-agent ablation
            # asymmetric: the single-agent arm kept those nodes and the
            # multi-agent arm did not, so the two arms differed by more
            # than the variable under test.
            served = {_ROLE_CAPABILITY[a.role] for a in gatherers}
            unserved = [c for c in data_caps if c not in served]
            for cap in unserved:
                graph.add_node(ExecutionNode(node_id=f"data_{cap.lower()}", capability=cap))
            evidence_nodes = tuple(
                [a.agent_id for a in gatherers] + [f"data_{c.lower()}" for c in unserved]
            )
        elif data_caps:
            for cap in data_caps:
                graph.add_node(ExecutionNode(node_id=f"data_{cap.lower()}", capability=cap))
            evidence_nodes = tuple(f"data_{c.lower()}" for c in data_caps)
        else:
            evidence_nodes = ()

        if evidence_nodes:
            graph.add_node(ExecutionNode(
                node_id="merge", capability="merge", depends_on=evidence_nodes,
                # Answer from whatever evidence arrived. One failing
                # source must not block generation when another
                # returned good evidence (graceful degradation).
                requires_all_dependencies=False,
            ))
            graph.add_node(ExecutionNode(node_id="generation", capability="generation", depends_on=("merge",)))
        else:
            graph.add_node(ExecutionNode(node_id="generation", capability="generation"))

        if agent_selected:
            # The actor must not act before the answer it may act on
            # exists. Its id is the established "agent_action".
            actor = next((a for a in (agent_plan.agents if agent_plan else [])
                          if a.role is AgentRole.NOTIFIER), None)
            actor_id = actor.agent_id if actor else "agent_action"
            depends = tuple(sorted({"generation", *(a.agent_id for a in gatherers)}))
            graph.add_node(ExecutionNode(
                node_id=actor_id, capability=CapabilityHint.AGENT.value,
                depends_on=depends, requires_all_dependencies=False,
                input_ref={"agent_id": actor_id, "role": "NOTIFIER"},
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
