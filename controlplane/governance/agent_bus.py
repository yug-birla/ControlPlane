"""Agent-to-agent communication, mediated by ControlPlane.

Milestone 12 (§8-§10). ``AgentMessage`` has existed since Milestone 10 as
a data structure, but nothing produced or recorded one -- so agents could
not actually communicate, and the "no hidden agent channel" guarantee was
a claim rather than a property.

THE RULE THIS ENFORCES:

    An agent may *request*. It may never *act on the global plan*.

So this bus does two things and deliberately refuses a third:

1. It CARRIES structured messages between agents (handoffs, evidence,
   uncertainty, failures) and records every one on the event stream, so
   there is no path by which two agents exchange anything unobserved.

2. It TRIAGES a ``REPLAN_REQUEST`` into a recommendation -- accept,
   reject, or needs-review -- based on what the requesting agent actually
   observed.

3. It does NOT replan. ``Replanner`` proposes graph changes and the
   Decision Engine decides. A bus that could mutate the plan would hand
   an agent exactly the authority the architecture forbids it.

WHY TRIAGE LIVES HERE AND NOT IN THE REPLANNER: an agent's request is a
*claim* ("I could not answer with what I have"). Deciding whether that
claim is credible is a governance question about the agent, distinct
from the planning question of what a new graph should look like. Keeping
them apart is what stops a persuasive-but-wrong agent from steering the
plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from controlplane.governance.multi_agent import AgentMessage, AgentMessageType


class RequestTriage(str, Enum):
    ACCEPT = "ACCEPT"
    """The agent's claim is corroborated by what it actually produced."""

    REJECT = "REJECT"
    """The agent asked for more while having produced usable output, or
    has already asked and been served."""

    NEEDS_REVIEW = "NEEDS_REVIEW"
    """Cannot be adjudicated from the recorded evidence alone."""


# An agent gets one replan request per request lifecycle. Without this an
# agent that always claims insufficiency would loop forever, which is the
# unbounded-autonomy failure the architecture explicitly forbids.
MAX_REPLAN_REQUESTS_PER_AGENT = 1


@dataclass
class TriageResult:
    triage: RequestTriage
    reason: str
    requested_capability: str | None = None

    def to_dict(self) -> dict:
        return {
            "triage": self.triage.value,
            "reason": self.reason,
            "requested_capability": self.requested_capability,
        }


@dataclass
class AgentBus:
    """Records agent communication and triages agent requests.

    Holds no authority of its own: everything it produces is an input to
    ControlPlane's decision, never a decision.
    """

    messages: list[AgentMessage] = field(default_factory=list)
    _replan_requests: dict[str, int] = field(default_factory=dict)

    def send(self, message: AgentMessage) -> AgentMessage:
        """Record one message. Every message is observable by construction."""
        self.messages.append(message)
        if message.message_type is AgentMessageType.REPLAN_REQUEST:
            self._replan_requests[message.from_agent] = (
                self._replan_requests.get(message.from_agent, 0) + 1
            )
        return message

    def messages_for(self, agent_id: str) -> list[AgentMessage]:
        return [m for m in self.messages if m.to_agent == agent_id]

    def handoffs(self) -> list[AgentMessage]:
        return [m for m in self.messages if m.message_type is AgentMessageType.HANDOFF]

    def triage_replan_request(
        self,
        message: AgentMessage,
        *,
        agent_produced_evidence: bool,
        available_capabilities: set[str] | None = None,
        requested_capability: str | None = None,
    ) -> TriageResult:
        """Decide whether an agent's replan request is credible.

        ``agent_produced_evidence`` is the corroboration: an agent that
        returned usable evidence and *also* claims it could not proceed is
        contradicting its own output, and its request is rejected. This is
        deliberately grounded in what the agent DID rather than in how its
        message is worded -- otherwise the persuasiveness of the claim,
        rather than its truth, would steer the plan.
        """
        if message.message_type is not AgentMessageType.REPLAN_REQUEST:
            return TriageResult(
                triage=RequestTriage.REJECT,
                reason=f"not a replan request (got {message.message_type.value})",
            )

        if self._replan_requests.get(message.from_agent, 0) > MAX_REPLAN_REQUESTS_PER_AGENT:
            return TriageResult(
                triage=RequestTriage.REJECT,
                reason=(
                    f"{message.from_agent} has exceeded {MAX_REPLAN_REQUESTS_PER_AGENT} "
                    "replan request(s); an agent that can request unboundedly can loop"
                ),
            )

        if agent_produced_evidence:
            return TriageResult(
                triage=RequestTriage.REJECT,
                reason=(
                    f"{message.from_agent} produced usable evidence, which contradicts its "
                    "claim that it could not proceed -- the request is not corroborated by "
                    "its own output"
                ),
            )

        if requested_capability is not None:
            available = available_capabilities or set()
            if requested_capability not in available:
                return TriageResult(
                    triage=RequestTriage.NEEDS_REVIEW,
                    reason=(
                        f"{message.from_agent} asked for {requested_capability!r}, which is "
                        "not available or not permitted here; ControlPlane must decide "
                        "whether to abstain, degrade, or escalate"
                    ),
                    requested_capability=requested_capability,
                )
            return TriageResult(
                triage=RequestTriage.ACCEPT,
                reason=(
                    f"{message.from_agent} produced no usable evidence and "
                    f"{requested_capability!r} is available to serve the gap"
                ),
                requested_capability=requested_capability,
            )

        return TriageResult(
            triage=RequestTriage.ACCEPT,
            reason=f"{message.from_agent} produced no usable evidence; a replan is warranted",
        )


def evidence_handoff(
    *, from_agent: str, to_agent: str, evidence_count: int, sensitivity
) -> AgentMessage:
    """The common case: one agent passes gathered evidence to another.

    Carries the data's sensitivity, so composition governance sees the
    same classification the handing-off agent saw rather than
    re-deriving it.
    """
    return AgentMessage(
        message_type=AgentMessageType.HANDOFF,
        from_agent=from_agent,
        to_agent=to_agent,
        payload_summary=f"{evidence_count} evidence item(s)",
        data_sensitivity=sensitivity,
    )
