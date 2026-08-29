"""Agent-to-agent communication.

The property under test: an agent may REQUEST but never ACT on the
global plan, and no agent communication is unobserved.
"""

from __future__ import annotations

from controlplane.governance.agent_bus import (
    MAX_REPLAN_REQUESTS_PER_AGENT,
    AgentBus,
    RequestTriage,
    evidence_handoff,
)
from controlplane.governance.multi_agent import (
    AgentMessage,
    AgentMessageType,
    DataSensitivity,
)


def _replan_request(from_agent: str = "agent_retriever") -> AgentMessage:
    return AgentMessage(
        message_type=AgentMessageType.REPLAN_REQUEST,
        from_agent=from_agent, to_agent=None,
        payload_summary="retrieval returned no usable evidence",
    )


def test_every_message_is_recorded_so_there_is_no_hidden_channel():
    bus = AgentBus()
    bus.send(evidence_handoff(from_agent="a", to_agent="b", evidence_count=3,
                              sensitivity=DataSensitivity.INTERNAL))
    assert len(bus.messages) == 1
    assert bus.messages_for("b")[0].from_agent == "a"


def test_a_handoff_carries_the_data_sensitivity_the_sender_saw():
    """Composition governance must see the same classification the
    handing-off agent saw, not re-derive it downstream."""
    message = evidence_handoff(from_agent="agent_analyst", to_agent="agent_action",
                               evidence_count=2, sensitivity=DataSensitivity.CONFIDENTIAL)
    assert message.data_sensitivity is DataSensitivity.CONFIDENTIAL
    assert message.message_type is AgentMessageType.HANDOFF


def test_a_replan_request_from_an_agent_with_no_evidence_is_accepted():
    bus = AgentBus()
    request = bus.send(_replan_request())
    result = bus.triage_replan_request(request, agent_produced_evidence=False)
    assert result.triage is RequestTriage.ACCEPT


def test_an_agent_that_produced_evidence_cannot_claim_it_could_not_proceed():
    """Triage is grounded in what the agent DID, not in how its message is
    worded -- otherwise the persuasiveness of a claim, rather than its
    truth, would steer the plan."""
    bus = AgentBus()
    request = bus.send(_replan_request())
    result = bus.triage_replan_request(request, agent_produced_evidence=True)
    assert result.triage is RequestTriage.REJECT
    assert "contradicts" in result.reason


def test_replan_requests_are_bounded_per_agent():
    """An agent that can request unboundedly can loop -- the unbounded
    autonomy the architecture forbids."""
    bus = AgentBus()
    for _ in range(MAX_REPLAN_REQUESTS_PER_AGENT + 1):
        request = bus.send(_replan_request())
    result = bus.triage_replan_request(request, agent_produced_evidence=False)
    assert result.triage is RequestTriage.REJECT
    assert "exceeded" in result.reason


def test_requesting_an_unavailable_capability_needs_review_not_silent_acceptance():
    bus = AgentBus()
    request = bus.send(_replan_request())
    result = bus.triage_replan_request(
        request, agent_produced_evidence=False,
        requested_capability="WEB", available_capabilities={"RAG", "SQL"},
    )
    assert result.triage is RequestTriage.NEEDS_REVIEW
    assert result.requested_capability == "WEB"


def test_requesting_an_available_capability_is_accepted():
    bus = AgentBus()
    request = bus.send(_replan_request())
    result = bus.triage_replan_request(
        request, agent_produced_evidence=False,
        requested_capability="SQL", available_capabilities={"RAG", "SQL"},
    )
    assert result.triage is RequestTriage.ACCEPT
    assert result.requested_capability == "SQL"


def test_a_non_replan_message_is_not_triaged_as_one():
    bus = AgentBus()
    handoff = bus.send(evidence_handoff(from_agent="a", to_agent="b", evidence_count=1,
                                        sensitivity=DataSensitivity.PUBLIC))
    result = bus.triage_replan_request(handoff, agent_produced_evidence=False)
    assert result.triage is RequestTriage.REJECT


def test_the_bus_cannot_change_the_plan():
    """The authority boundary, asserted structurally: the bus exposes no
    method that mutates a plan or a graph, and triage returns a
    recommendation rather than an action."""
    bus = AgentBus()
    for forbidden in ("replan", "apply", "mutate_plan", "set_graph", "execute"):
        assert not hasattr(bus, forbidden), f"AgentBus must not expose {forbidden}()"

    request = bus.send(_replan_request())
    result = bus.triage_replan_request(request, agent_produced_evidence=False)
    assert isinstance(result.triage, RequestTriage)  # a recommendation, not an effect
