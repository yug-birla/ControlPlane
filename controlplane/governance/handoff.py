"""What one agent actually hands to the next.

THE DEFECT THIS EXISTS TO FIX. Agent handoff messages were synthesized
*after every agent had already run*. The runtime executed the gatherers
and the actor, collected the results, and only then constructed
``HANDOFF`` messages describing an exchange that had never taken place.
``AgentCapability.execute`` took the query string and nothing else, so
the actor could not have used a handoff even if one had arrived in time.

That is the "fake multi-agent" shape the directive names: agents that
produce output in parallel, a merge, and a record of communication that
changed nothing. It also explains why the communication ablation found
no effect. There was no effect to find -- the messages were a
post-execution log, and the two arms differed only in whether that log
was written.

WHAT CHANGES. The bus becomes the channel rather than the transcript. A
gatherer's evidence is handed over at the moment the actor runs, through
``AgentBus``, and the actor reads its own inbox. Suppressing the bus now
genuinely deprives the actor of evidence, which is what makes the
no-communication condition a real control rather than a logging flag.

WHAT IS HANDED OVER, AND WHAT IS NOT. Not the upstream trajectory, not
raw payloads: a structured summary -- which agents contributed, which
capabilities they served, how many items, the highest sensitivity
involved, and a short capped digest. Passing everything would be the
other failure mode, inflating context and cost for no gain.

WHY SENSITIVITY TRAVELS WITH IT. It is the field that changes the
receiver's behaviour. An agent proposing an external send after being
handed CONFIDENTIAL records is doing something materially different from
one proposing the same send with nothing in hand, and ``AgentGate``
could not previously tell those apart: it saw a tool call and a static
risk label, never the data the call would carry. Composition risk was
assessed only *after* execution. Carrying sensitivity into the gate lets
the same judgement happen before anything runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from controlplane.governance.multi_agent import (
    _TOOL_DATA_SENSITIVITY,
    AgentMessage,
    AgentMessageType,
    DataSensitivity,
)

MAX_DIGEST_ITEMS = 3
"""Enough for a receiver to act on, few enough that a large retrieval
does not become a large prompt. §37: build targeted context."""

MAX_DIGEST_CHARS = 240

_SENSITIVITY_ORDER = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.CONFIDENTIAL: 2,
    DataSensitivity.RESTRICTED: 3,
}

_SENSITIVE = {DataSensitivity.CONFIDENTIAL, DataSensitivity.RESTRICTED}

# The same mapping ``steps_from_agent_results`` uses, so the gate and the
# composition governor classify a gatherer's output identically rather
# than deriving sensitivity two ways and disagreeing.
_CAPABILITY_TOOL = {"SQL": "sql_read_query", "RAG": "read_documents"}


@dataclass(frozen=True)
class HandoffContext:
    """The structured context an agent receives from its predecessors."""

    from_agents: tuple[str, ...]
    sources: tuple[str, ...]
    evidence_count: int
    max_sensitivity: DataSensitivity
    evidence_digest: tuple[str, ...]

    @property
    def carries_sensitive_data(self) -> bool:
        return self.max_sensitivity in _SENSITIVE

    def to_dict(self) -> dict:
        return {
            "from_agents": list(self.from_agents),
            "sources": list(self.sources),
            "evidence_count": self.evidence_count,
            "max_sensitivity": self.max_sensitivity.value,
            "carries_sensitive_data": self.carries_sensitive_data,
            "digest_item_count": len(self.evidence_digest),
        }


def evidence_items(result: dict) -> list:
    """The evidence a gatherer produced, whatever shape it came back in.

    RAG returns ``evidence``, SQL returns ``rows``; ``chunks`` is the
    older RAG key kept as a fallback. Reading only one of these was the
    Milestone-14 defect that made every MCP evidence count zero.
    """
    for key in ("evidence", "rows", "chunks"):
        value = result.get(key)
        if value:
            return list(value)
    return []


def sensitivity_of(result: dict) -> DataSensitivity:
    serves = result.get("serves_capability")
    tool = _CAPABILITY_TOOL.get(serves, result.get("proposed_tool", ""))
    return _TOOL_DATA_SENSITIVITY.get(tool, DataSensitivity.PUBLIC)


def _digest(items: list) -> tuple[str, ...]:
    out = []
    for item in items[:MAX_DIGEST_ITEMS]:
        if isinstance(item, dict):
            text = item.get("text") or item.get("content") or str(item)
        else:
            text = str(item)
        text = " ".join(text.split())
        out.append(text[:MAX_DIGEST_CHARS])
    return tuple(out)


def handoff_messages_for(
    *, to_agent: str, upstream: list[tuple[str, dict]]
) -> list[AgentMessage]:
    """One HANDOFF message per upstream agent that produced evidence.

    Built at the moment of handoff, from results that already exist,
    rather than reconstructed afterwards.
    """
    messages = []
    for agent_id, result in upstream:
        items = evidence_items(result)
        if not items:
            continue
        messages.append(
            AgentMessage(
                message_type=AgentMessageType.HANDOFF,
                from_agent=agent_id,
                to_agent=to_agent,
                payload_summary=f"{len(items)} evidence item(s)",
                data_sensitivity=sensitivity_of(result),
            )
        )
    return messages


def build_handoff_context(
    *, delivered: list[AgentMessage], upstream: list[tuple[str, dict]]
) -> HandoffContext | None:
    """Assemble what the receiving agent knows.

    ``delivered`` gates this deliberately: only agents whose message
    actually arrived contribute. A suppressed bus therefore yields
    ``None``, and the receiver acts with nothing -- which is what makes
    the no-communication arm a real control instead of a logging switch.
    """
    if not delivered:
        return None

    senders = {m.from_agent for m in delivered if m.message_type is AgentMessageType.HANDOFF}
    if not senders:
        return None

    contributing = [(agent_id, r) for agent_id, r in upstream if agent_id in senders]
    if not contributing:
        return None

    items: list = []
    sources: list[str] = []
    max_sensitivity = DataSensitivity.PUBLIC
    for agent_id, result in contributing:
        items.extend(evidence_items(result))
        serves = result.get("serves_capability")
        if serves and serves not in sources:
            sources.append(serves)
        sensitivity = sensitivity_of(result)
        if _SENSITIVITY_ORDER[sensitivity] > _SENSITIVITY_ORDER[max_sensitivity]:
            max_sensitivity = sensitivity

    return HandoffContext(
        from_agents=tuple(agent_id for agent_id, _ in contributing),
        sources=tuple(sources),
        evidence_count=len(items),
        max_sensitivity=max_sensitivity,
        evidence_digest=_digest(items),
    )
