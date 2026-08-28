"""Multi-agent composition governance.

THE GOVERNANCE INSIGHT THIS EXISTS FOR (Milestone 10 §51: "Do not
evaluate only individual agents"):

A chain of agents can be **individually safe but collectively unsafe**.
Each hop passes its own gate; the composition is what creates the risk.

    Agent A   reads customer PII from the database      -> ALLOW (read-only, permitted)
    Agent B   receives A's output, sends a notification  -> ALLOW (notification is permitted)
    ---------------------------------------------------------------------------
    Composition: sensitive data reaches an external destination.

``AgentGate`` (Milestone 6) evaluates ONE proposed step against its own
risk. It is correct and stays unchanged. It structurally cannot see this,
because neither step is individually wrong -- the exfiltration path only
exists in the *sequence*. That is the gap this module closes.

WHAT IT IS NOT: it is not a second authorization system, and it does not
replace ``AgentGate``. It produces a composition-level assessment that
the Decision Engine consumes alongside per-step governance, in exactly
the way ``AgentGovernancePassthroughEvaluator`` already surfaces per-step
outcomes. ControlPlane remains the only authority.

AUTHORITY BOUNDARY: agents may *request* things (a capability, a replan,
an approval) but may never mutate the plan or grant themselves
permissions. Requests are represented here as data; ControlPlane decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentRole(str, Enum):
    RETRIEVER = "RETRIEVER"
    ANALYST = "ANALYST"
    NOTIFIER = "NOTIFIER"
    VERIFIER = "VERIFIER"


class DataSensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class DestinationClass(str, Enum):
    NONE = "NONE"
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


class CompositionRisk(str, Enum):
    NONE = "NONE"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


class AgentMessageType(str, Enum):
    """Structured agent-to-agent communication, mediated by ControlPlane.

    Agents never call each other directly; a message is data that
    ControlPlane routes, records on the trajectory, and may act on.
    """

    RESULT = "RESULT"
    EVIDENCE = "EVIDENCE"
    FAILURE = "FAILURE"
    UNCERTAINTY = "UNCERTAINTY"
    CAPABILITY_REQUEST = "CAPABILITY_REQUEST"
    HANDOFF = "HANDOFF"
    REPLAN_REQUEST = "REPLAN_REQUEST"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    TOOL_RESULT = "TOOL_RESULT"


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    role: AgentRole
    parent_agent: str | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "parent_agent": self.parent_agent,
            "permissions": sorted(self.permissions),
        }


@dataclass
class AgentMessage:
    """One structured communication between agents, via ControlPlane."""

    message_type: AgentMessageType
    from_agent: str
    to_agent: str | None
    payload_summary: str
    data_sensitivity: DataSensitivity = DataSensitivity.PUBLIC

    def to_dict(self) -> dict:
        return {
            "message_type": self.message_type.value,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "payload_summary": self.payload_summary,
            "data_sensitivity": self.data_sensitivity.value,
        }


@dataclass
class AgentStep:
    """One agent's governed action within a composed trajectory."""

    agent: AgentIdentity
    tool: str
    governance_action: str
    """The per-step AgentGate outcome -- ALLOW/RESTRICT/HUMAN_REVIEW/BLOCK."""
    data_sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    destination: DestinationClass = DestinationClass.NONE
    executed: bool = True

    def to_dict(self) -> dict:
        return {
            "agent": self.agent.to_dict(),
            "tool": self.tool,
            "governance_action": self.governance_action,
            "data_sensitivity": self.data_sensitivity.value,
            "destination": self.destination.value,
            "executed": self.executed,
        }


@dataclass
class CompositionAssessment:
    risk: CompositionRisk
    reason: str
    recommended_action: str
    """ALLOW / HUMAN_REVIEW / BLOCK -- a recommendation to the Decision
    Engine, never an enforcement action taken here."""
    sensitive_data_reached_external: bool = False
    cumulative_permissions: frozenset[str] = field(default_factory=frozenset)
    agent_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "risk": self.risk.value,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "sensitive_data_reached_external": self.sensitive_data_reached_external,
            "cumulative_permissions": sorted(self.cumulative_permissions),
            "agent_chain": self.agent_chain,
        }


_SENSITIVE = {DataSensitivity.CONFIDENTIAL, DataSensitivity.RESTRICTED}


class CompositionGovernor:
    """Evaluates a COMPOSED agent trajectory, not individual steps."""

    name = "composition_v1"

    def evaluate(self, steps: list[AgentStep]) -> CompositionAssessment:
        chain = [s.agent.agent_id for s in steps]
        cumulative = frozenset().union(*(s.agent.permissions for s in steps)) if steps else frozenset()

        if not steps:
            return CompositionAssessment(
                risk=CompositionRisk.NONE, reason="no agent steps to evaluate",
                recommended_action="ALLOW", agent_chain=chain,
            )

        # Only steps that actually ran can move data. A BLOCKED or
        # awaiting-approval step has not exfiltrated anything, and
        # counting it would manufacture a risk the system already
        # prevented.
        executed = [s for s in steps if s.executed]

        touched_sensitive = any(s.data_sensitivity in _SENSITIVE for s in executed)
        first_sensitive_index = next(
            (i for i, s in enumerate(executed) if s.data_sensitivity in _SENSITIVE), None
        )
        external_after_sensitive = first_sensitive_index is not None and any(
            s.destination is DestinationClass.EXTERNAL
            for s in executed[first_sensitive_index:]
        )

        if external_after_sensitive:
            return CompositionAssessment(
                risk=CompositionRisk.CRITICAL,
                reason=(
                    "sensitive data was accessed earlier in this agent chain and a later "
                    "agent sent to an EXTERNAL destination. Each step was individually "
                    "permitted; the exfiltration path exists only in the composition, which "
                    "is why per-step gating cannot detect it"
                ),
                recommended_action="BLOCK",
                sensitive_data_reached_external=True,
                cumulative_permissions=cumulative,
                agent_chain=chain,
            )

        # Broad accumulated authority across a chain is worth surfacing
        # even without a concrete exfiltration path: no single agent holds
        # it, so no single gate ever saw it.
        if len(cumulative) >= 3 and len({s.agent.agent_id for s in executed}) >= 2:
            return CompositionAssessment(
                risk=CompositionRisk.ELEVATED,
                reason=(
                    f"the chain accumulated {len(cumulative)} distinct permissions across "
                    f"{len({s.agent.agent_id for s in executed})} agents; no individual agent "
                    "holds this combined authority, so no per-step gate evaluated it"
                ),
                recommended_action="HUMAN_REVIEW",
                cumulative_permissions=cumulative,
                agent_chain=chain,
            )

        if touched_sensitive:
            return CompositionAssessment(
                risk=CompositionRisk.ELEVATED,
                reason="sensitive data was accessed but never reached an external destination",
                recommended_action="ALLOW",
                cumulative_permissions=cumulative,
                agent_chain=chain,
            )

        return CompositionAssessment(
            risk=CompositionRisk.NONE,
            reason="no sensitive data flow and no unusual accumulated authority in this chain",
            recommended_action="ALLOW",
            cumulative_permissions=cumulative,
            agent_chain=chain,
        )
