"""Multi-agent planning: decide how many agents a task actually needs.

Milestone 11 (§28/§31/§35). Multi-agent *governance* has existed since
Milestone 10 -- ``CompositionGovernor`` evaluates an agent chain and
catches compositions that are individually safe but collectively unsafe.
But the planner could only ever emit ONE agent node, so that governance
had nothing real to govern.

THE RULE THE SPEC IS EXPLICIT ABOUT:

    "Do not always use one agent. Do not always use three agents. Use the
     minimum number justified by task requirements."

So this is a planner, not a template. The agent count is DERIVED from the
query's own measured data requirements and actionability:

    one data requirement, no action     -> 0 agents (plain capability path)
    one action                          -> 1 agent
    two independent data requirements   -> 2 agents, PARALLEL
    data + action                       -> agents with a real dependency

An agent is only introduced when it does something a plain capability
node would not: it holds a distinct role and permission set, and its
actions are individually gated and then collectively governed.

WHAT THIS DOES NOT DO. It does not execute agents, does not grant
permissions, and does not decide whether a proposed action is allowed --
``AgentGate`` gates each step and ``CompositionGovernor`` evaluates the
chain. It only decides the SHAPE of the agent plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from controlplane.capabilities.registry import CapabilityRegistry, get_capability_registry
from controlplane.execution.graph import ExecutionGraph, ExecutionNode
from controlplane.governance.multi_agent import AgentIdentity, AgentRole

# Which agent role naturally serves which data requirement. Used to give
# each planned agent a role and a permission set, so composition
# governance has real identities to reason about rather than N copies of
# an anonymous "agent".
_REQUIREMENT_ROLES: dict[str, tuple[AgentRole, str, frozenset[str]]] = {
    "RAG_CORPUS": (AgentRole.RETRIEVER, "RAG", frozenset({"read:documents"})),
    "SQL_DB": (AgentRole.ANALYST, "SQL", frozenset({"read:enterprise_db"})),
}


@dataclass
class AgentPlan:
    agents: list[AgentIdentity] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)
    """Node ids that may run concurrently. A group with more than one
    member is a real parallelism claim the executor can act on."""
    reason: str = ""

    @property
    def agent_count(self) -> int:
        return len(self.agents)

    def to_dict(self) -> dict:
        return {
            "agent_count": self.agent_count,
            "agents": [a.to_dict() for a in self.agents],
            "node_ids": self.node_ids,
            "parallel_groups": self.parallel_groups,
            "reason": self.reason,
        }


class AgentPlanner:
    name = "agent_planner_v1"

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry or get_capability_registry()

    def plan(
        self,
        *,
        data_requirements: set[str],
        is_agentic: bool,
        restricted_capabilities: set[str] | None = None,
    ) -> AgentPlan:
        """Decide the agent shape for this task.

        ``is_agentic`` comes from the Query Profiler's measured
        actionability, not from a keyword scan performed here.
        """
        restricted = restricted_capabilities or set()

        # Data-gathering agents: one per INDEPENDENT, servable requirement.
        gatherers: list[AgentIdentity] = []
        node_ids: list[str] = []
        for requirement in sorted(data_requirements):
            mapping = _REQUIREMENT_ROLES.get(requirement)
            if mapping is None:
                continue
            role, capability_id, permissions = mapping
            if capability_id in restricted:
                continue
            descriptor = self._registry.get(capability_id)
            if descriptor is None or descriptor.status.value != "AVAILABLE":
                # Never plan an agent around a MOCKED capability: it would
                # produce a plan that cannot supply what it promises.
                continue
            agent_id = f"agent_{role.value.lower()}"
            gatherers.append(AgentIdentity(agent_id=agent_id, role=role, permissions=permissions))
            node_ids.append(agent_id)

        # A single data source does not justify an agent at all -- a plain
        # capability node does the same work without the governance
        # overhead of an identity, permissions, and a gated proposal.
        if len(gatherers) < 2 and not is_agentic:
            return AgentPlan(
                reason=(
                    f"{len(gatherers)} independent data source(s) and no action required -- "
                    "a plain capability path does this work without agent overhead"
                )
            )

        agents = list(gatherers) if len(gatherers) >= 2 else []
        ids = list(node_ids) if len(gatherers) >= 2 else []

        # Independent gatherers are a genuine parallel group.
        parallel_groups = [list(ids)] if len(ids) > 1 else []

        if is_agentic:
            # The actor depends on every gatherer: it must not act before
            # the evidence it is acting on has arrived.
            actor = AgentIdentity(
                agent_id="agent_actor",
                role=AgentRole.NOTIFIER,
                parent_agent=ids[-1] if ids else None,
                permissions=frozenset({"execute:tools"}),
            )
            agents.append(actor)
            ids.append(actor.agent_id)

        if not agents:
            return AgentPlan(reason="no agent is justified for this task")

        return AgentPlan(
            agents=agents, node_ids=ids, parallel_groups=parallel_groups,
            reason=(
                f"{len(agents)} agent(s): "
                f"{len(gatherers) if len(gatherers) >= 2 else 0} independent gatherer(s)"
                f"{' running in parallel' if parallel_groups else ''}"
                f"{', plus one actor for the requested action' if is_agentic else ''}"
            ),
        )

    def apply(self, graph: ExecutionGraph, plan: AgentPlan) -> list[str]:
        """Add the planned agent nodes to the graph.

        Gatherers have no dependencies on each other, which is what makes
        them schedulable in parallel by the existing wave scheduler -- the
        parallelism is a property of the DEPENDENCY STRUCTURE, not a flag
        the planner sets and hopes something honours.
        """
        added: list[str] = []
        gatherer_ids = [a.agent_id for a in plan.agents if a.role is not AgentRole.NOTIFIER]

        for agent in plan.agents:
            if any(n.node_id == agent.agent_id for n in graph.nodes):
                continue
            depends_on: tuple[str, ...] = ()
            if agent.role is AgentRole.NOTIFIER and gatherer_ids:
                depends_on = tuple(gatherer_ids)
            graph.add_node(ExecutionNode(
                node_id=agent.agent_id, capability="AGENT", depends_on=depends_on,
                # An actor should still act on whatever evidence arrived
                # rather than being blocked entirely by one failed gatherer.
                requires_all_dependencies=False if depends_on else True,
                input_ref={"agent_id": agent.agent_id, "role": agent.role.value},
            ))
            added.append(agent.agent_id)

        if added:
            graph.validate()
        return added
