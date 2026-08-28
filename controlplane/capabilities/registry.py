"""Capability Registry -- centralized capability metadata.

Milestone 10 (§41). Before this, capability knowledge was scattered:
``CapabilityHint`` in the fingerprint enum, a hard-coded
``_DATA_CAPABILITIES`` set in the capability router, a handler dict in
the runtime, and policy restriction lists in the policy baseline. Nothing
could answer the question the architecture actually needs answered:

    "What capabilities are available, what can each of them do, and which
     ones could supply the evidence this query still needs?"

That question is what makes planning DISCOVERY-DRIVEN rather than
hard-coded, and it is the prerequisite for dynamic replanning that adds
a genuinely new capability instead of re-running the same node with a
bigger ``k``.

WHAT THIS IS NOT: it is not the ``model_registry`` Postgres table (that
holds MODEL metadata -- see ``controlplane/models/registry_seed.py``),
and it is not an MCP server. It is the in-process source of truth for
capability metadata, which an MCP capability fabric would later populate
from discovery rather than replace.

BOUNDARY (non-negotiable per every architecture doc in this repo):
this registry describes HOW to reach a capability and WHAT it can do.
ControlPlane still decides WHETHER, WHEN, and WHICH. Nothing in this
module makes a control decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache


class CapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    MOCKED = "MOCKED"
    """Reachable and wired, but returns a placeholder result -- the
    executor's explicit MOCKED handler. Distinguished from UNAVAILABLE so
    the planner can avoid *relying* on it for evidence while still being
    honest that the node runs."""


class SideEffectLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    WRITE_INTERNAL = "WRITE_INTERNAL"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    name: str
    description: str
    status: CapabilityStatus
    side_effect_level: SideEffectLevel
    supplies_evidence: bool
    """True when this capability can contribute EVIDENCE to a generation
    prompt. The replanner only considers evidence-supplying capabilities
    when the problem is insufficient evidence."""
    satisfies_data_requirements: frozenset[str] = field(default_factory=frozenset)
    """``DataRequirement`` values this capability can serve. This is what
    makes alternative-capability selection a lookup against the query's
    own measured data requirements rather than a hard-coded
    'RAG failed -> try SQL' rule."""
    required_permissions: frozenset[str] = field(default_factory=frozenset)
    latency_class: str = "MEDIUM"
    cost_class: str = "MEDIUM"
    risk_class: str = "LOW"
    provider: str = "internal"
    """"internal" for a direct in-process implementation; an MCP server
    id once a capability is reached through the MCP fabric."""

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "side_effect_level": self.side_effect_level.value,
            "supplies_evidence": self.supplies_evidence,
            "satisfies_data_requirements": sorted(self.satisfies_data_requirements),
            "required_permissions": sorted(self.required_permissions),
            "latency_class": self.latency_class,
            "cost_class": self.cost_class,
            "risk_class": self.risk_class,
            "provider": self.provider,
        }


# The descriptors mirror what is ACTUALLY implemented in
# controlplane/capabilities/ and controlplane/execution/executor.py.
# Status here must never be more optimistic than reality -- a registry
# that claims a capability works when it returns a placeholder would make
# the planner choose it and then silently produce no evidence.
_DESCRIPTORS: tuple[CapabilityDescriptor, ...] = (
    CapabilityDescriptor(
        capability_id="RAG",
        name="Enterprise document retrieval",
        description="Dense + BM25 retrieval over the enterprise corpus, fused with RRF "
                    "and reranked by a cross-encoder.",
        status=CapabilityStatus.AVAILABLE,
        side_effect_level=SideEffectLevel.READ_ONLY,
        supplies_evidence=True,
        satisfies_data_requirements=frozenset({"RAG_CORPUS"}),
        latency_class="MEDIUM", cost_class="LOW", risk_class="LOW",
    ),
    CapabilityDescriptor(
        capability_id="SQL",
        name="Structured enterprise data query",
        description="Fixed, human-reviewable SQL templates with parameterized entity "
                    "filtering over the enterprise demo database. Never LLM-generated SQL.",
        status=CapabilityStatus.AVAILABLE,
        side_effect_level=SideEffectLevel.READ_ONLY,
        supplies_evidence=True,
        satisfies_data_requirements=frozenset({"SQL_DB"}),
        required_permissions=frozenset({"read:enterprise_db"}),
        latency_class="LOW", cost_class="LOW", risk_class="LOW",
    ),
    CapabilityDescriptor(
        capability_id="AGENT",
        name="Governed tool execution",
        description="Proposes and executes real tools, each gated by AgentGate before "
                    "running. Destructive operations are hard-blocked.",
        status=CapabilityStatus.AVAILABLE,
        side_effect_level=SideEffectLevel.EXTERNAL_ACTION,
        supplies_evidence=False,
        required_permissions=frozenset({"execute:tools"}),
        latency_class="HIGH", cost_class="MEDIUM", risk_class="HIGH",
    ),
    CapabilityDescriptor(
        capability_id="GENERAL",
        name="Direct model generation",
        description="Answer from the model's own parametric knowledge, with no external evidence.",
        status=CapabilityStatus.AVAILABLE,
        side_effect_level=SideEffectLevel.READ_ONLY,
        supplies_evidence=False,
        latency_class="MEDIUM", cost_class="MEDIUM", risk_class="LOW",
    ),
    # Honestly MOCKED -- these run via the executor's placeholder handler.
    # Registered rather than hidden so the planner knows they exist and
    # knows not to depend on them for evidence.
    CapabilityDescriptor(
        capability_id="CHAT_HISTORY",
        name="Conversation history retrieval",
        description="Prior-turn retrieval. Placeholder handler; no real conversation store yet.",
        status=CapabilityStatus.MOCKED,
        side_effect_level=SideEffectLevel.READ_ONLY,
        supplies_evidence=True,
        satisfies_data_requirements=frozenset({"CHAT_DATABASE"}),
        latency_class="LOW", cost_class="LOW", risk_class="LOW",
    ),
    CapabilityDescriptor(
        capability_id="MEMORY",
        name="Long-term memory",
        description="Durable user preference/memory store. Placeholder handler; no real store yet.",
        status=CapabilityStatus.MOCKED,
        side_effect_level=SideEffectLevel.READ_ONLY,
        supplies_evidence=True,
        satisfies_data_requirements=frozenset({"MEMORY_STORE"}),
        latency_class="LOW", cost_class="LOW", risk_class="LOW",
    ),
    CapabilityDescriptor(
        capability_id="WEB",
        name="External web retrieval",
        description="Public web search. Placeholder handler; no real web access is configured.",
        status=CapabilityStatus.MOCKED,
        side_effect_level=SideEffectLevel.READ_ONLY,
        supplies_evidence=True,
        satisfies_data_requirements=frozenset({"WEB_SEARCH"}),
        latency_class="HIGH", cost_class="MEDIUM", risk_class="MEDIUM",
    ),
)


class CapabilityRegistry:
    def __init__(self, descriptors: tuple[CapabilityDescriptor, ...] = _DESCRIPTORS) -> None:
        self._by_id = {d.capability_id: d for d in descriptors}

    def all(self) -> list[CapabilityDescriptor]:
        return list(self._by_id.values())

    def get(self, capability_id: str) -> CapabilityDescriptor | None:
        return self._by_id.get(capability_id)

    def discover(
        self,
        *,
        data_requirements: set[str] | None = None,
        supplies_evidence: bool | None = None,
        exclude: set[str] | None = None,
        restricted: set[str] | None = None,
        usable_only: bool = True,
    ) -> list[CapabilityDescriptor]:
        """Find capabilities matching a need.

        This is the discovery primitive that makes replanning
        evidence-driven instead of hard-coded. A caller asks "what could
        satisfy SQL_DB that I haven't already tried and that policy
        allows?" -- it does not ask "what do I do when RAG fails?".

        ``usable_only`` excludes MOCKED/UNAVAILABLE capabilities, because
        a placeholder cannot actually supply the evidence that motivated
        the search.
        """
        exclude = exclude or set()
        restricted = restricted or set()
        results = []
        for descriptor in self._by_id.values():
            if descriptor.capability_id in exclude or descriptor.capability_id in restricted:
                continue
            if usable_only and descriptor.status is not CapabilityStatus.AVAILABLE:
                continue
            if supplies_evidence is not None and descriptor.supplies_evidence != supplies_evidence:
                continue
            if data_requirements is not None:
                if not (descriptor.satisfies_data_requirements & data_requirements):
                    continue
            results.append(descriptor)
        # Cheapest/fastest first -- a replan should prefer the least
        # expensive way to obtain the missing evidence.
        order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        return sorted(
            results,
            key=lambda d: (order.get(d.cost_class, 1), order.get(d.latency_class, 1), d.capability_id),
        )


@lru_cache(maxsize=1)
def get_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry()
