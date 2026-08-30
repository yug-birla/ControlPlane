"""Did this agent earn its place?

The multi-agent benchmark could report agent counts, message counts and
latency, and could not answer the only question that decides whether
decomposition was worth it: what did each agent actually add. An agent
that re-fetches what another agent already has costs latency, tokens and
a governance surface, and contributes nothing.

§11 is explicit that this must not collapse into one opaque score, so
the dimensions stay separate and the verdict is derived from them rather
than replacing them:

    evidence_contributed   how much this agent produced
    unique_evidence        how much of it no other agent also produced
    duplicate_evidence     the remainder
    information_gain       unique / contributed
    downstream_influence   whether what it handed over changed a
                           receiving agent's decision, taken from that
                           agent's recorded ``handoff_influence`` rather
                           than assumed from the existence of a message
    answer_influence       whether its unique evidence reached the final
                           answer

WHAT THE VERDICTS MEAN.

    ESSENTIAL     contributed something no one else did, and it reached
                  the answer or changed a downstream decision
    CONTRIBUTING  contributed something unique with no traceable effect
                  downstream -- useful, unproven
    REDUNDANT     everything it produced, another agent also produced
    INERT         produced nothing and influenced nothing

REDUNDANT and INERT are the ones worth acting on: they are the evidence
for planning FEWER agents next time, which is what §72's "minimum
necessary complexity" needs in order to be more than a slogan.

A DELIBERATE LIMIT. ``answer_influence`` is lexical overlap between an
agent's unique evidence and the final answer. That is a proxy: an answer
can be shaped by evidence it does not quote, and can coincidentally share
wording with evidence it ignored. It is reported as a separate dimension,
never folded into a headline number, and the verdict never rests on it
alone -- an agent with downstream influence is ESSENTIAL regardless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from controlplane.governance.handoff import evidence_items

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "for", "in", "on",
    "at", "and", "or", "our", "we", "this", "that", "it", "as", "be", "has",
    "have", "had", "by", "from", "with", "which", "who", "when",
}

MIN_OVERLAP_FOR_ANSWER_INFLUENCE = 0.30
"""Share of an evidence item's informative tokens that must appear in the
answer before it counts as having reached it. Chosen to be strict enough
that incidental shared vocabulary does not register, and stated here
rather than buried so it can be argued with."""


class ContributionVerdict(str, Enum):
    ESSENTIAL = "ESSENTIAL"
    CONTRIBUTING = "CONTRIBUTING"
    REDUNDANT = "REDUNDANT"
    INERT = "INERT"


@dataclass
class AgentContribution:
    agent_id: str
    role: str | None
    evidence_contributed: int
    unique_evidence: int
    duplicate_evidence: int
    information_gain: float
    downstream_influence: str
    answer_influence: bool
    latency_ms: float | None
    verdict: ContributionVerdict
    reason: str

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "evidence_contributed": self.evidence_contributed,
            "unique_evidence": self.unique_evidence,
            "duplicate_evidence": self.duplicate_evidence,
            "information_gain": round(self.information_gain, 3),
            "downstream_influence": self.downstream_influence,
            "answer_influence": self.answer_influence,
            "latency_ms": self.latency_ms,
            "verdict": self.verdict.value,
            "reason": self.reason,
        }


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _item_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("content") or item)
    return str(item)


def _fingerprint(item) -> str:
    """Normalised form used to decide whether two agents produced the
    same thing. Whitespace and case only -- two agents quoting the same
    passage with different spacing have not each contributed it."""
    return " ".join(_item_text(item).lower().split())


def _reached_answer(items: list, answer: str | None) -> bool:
    if not answer or not items:
        return False
    answer_tokens = _tokens(answer)
    if not answer_tokens:
        return False
    for item in items:
        item_tokens = _tokens(_item_text(item))
        if not item_tokens:
            continue
        overlap = len(item_tokens & answer_tokens) / len(item_tokens)
        if overlap >= MIN_OVERLAP_FOR_ANSWER_INFLUENCE:
            return True
    return False


def measure_contributions(
    *,
    agent_results: list[tuple[str, dict]],
    answer: str | None = None,
    latencies_ms: dict[str, float] | None = None,
) -> list[AgentContribution]:
    """One record per agent, from what the agents already recorded.

    ``agent_results`` is ``[(node_id, agent_output), ...]`` -- the same
    structure ``steps_from_agent_results`` consumes, so this adds no
    reporting obligation to the agents themselves.
    """
    latencies_ms = latencies_ms or {}

    produced: dict[str, list] = {}
    for agent_id, result in agent_results:
        produced[agent_id] = evidence_items(result)

    # How many DISTINCT agents produced each item.
    seen_by: dict[str, set[str]] = {}
    for agent_id, items in produced.items():
        for item in items:
            seen_by.setdefault(_fingerprint(item), set()).add(agent_id)

    # Which agents were told something by whom, and whether it mattered
    # to them. Taken from the receiver's own record, so a message that
    # arrived and changed nothing does not count as influence.
    influence_by_sender: dict[str, str] = {}
    for _, result in agent_results:
        received = result.get("handoff_received") or {}
        effect = result.get("handoff_influence", "NONE")
        for sender in received.get("from_agents", []):
            current = influence_by_sender.get(sender, "NONE")
            if _rank(effect) > _rank(current):
                influence_by_sender[sender] = effect

    contributions = []
    for agent_id, result in agent_results:
        items = produced[agent_id]
        unique_items = [i for i in items if len(seen_by.get(_fingerprint(i), set())) == 1]
        unique = len(unique_items)
        duplicate = len(items) - unique
        gain = unique / len(items) if items else 0.0

        downstream = influence_by_sender.get(agent_id, "NONE")
        changed_downstream = downstream in ("CHANGED_STEP_RISK", "CHANGED_TOOL_OUTPUT")
        reached = _reached_answer(unique_items, answer)

        if not items and downstream == "NONE":
            verdict = ContributionVerdict.INERT
            reason = "produced no evidence and influenced no downstream agent"
        elif items and unique == 0:
            verdict = ContributionVerdict.REDUNDANT
            reason = (
                f"all {len(items)} item(s) were also produced by another agent; "
                "this agent added no information the request did not already have"
            )
        elif changed_downstream or reached:
            verdict = ContributionVerdict.ESSENTIAL
            reason = (
                f"{unique} unique item(s), "
                + ("which changed a downstream agent's decision"
                   if changed_downstream else "which reached the final answer")
            )
        else:
            verdict = ContributionVerdict.CONTRIBUTING
            reason = f"{unique} unique item(s) with no traceable downstream or answer effect"

        contributions.append(
            AgentContribution(
                agent_id=agent_id,
                role=result.get("agent_role"),
                evidence_contributed=len(items),
                unique_evidence=unique,
                duplicate_evidence=duplicate,
                information_gain=gain,
                downstream_influence=downstream,
                answer_influence=reached,
                latency_ms=latencies_ms.get(agent_id),
                verdict=verdict,
                reason=reason,
            )
        )
    return contributions


def _rank(effect: str) -> int:
    return {"NONE": 0, "OBSERVED_ONLY": 1, "CHANGED_STEP_RISK": 2, "CHANGED_TOOL_OUTPUT": 2}.get(effect, 0)


def summarise(contributions: list[AgentContribution]) -> dict:
    """Request-level view: how much of this plan paid for itself."""
    n = len(contributions) or 1
    wasted = [c for c in contributions
              if c.verdict in (ContributionVerdict.REDUNDANT, ContributionVerdict.INERT)]
    return {
        "agent_count": len(contributions),
        "essential_count": sum(1 for c in contributions
                               if c.verdict is ContributionVerdict.ESSENTIAL),
        "contributing_count": sum(1 for c in contributions
                                  if c.verdict is ContributionVerdict.CONTRIBUTING),
        "redundant_count": sum(1 for c in contributions
                               if c.verdict is ContributionVerdict.REDUNDANT),
        "inert_count": sum(1 for c in contributions if c.verdict is ContributionVerdict.INERT),
        # The number the planner should be judged on: agents that could
        # have been left out without losing anything measurable.
        "wasted_agent_rate": len(wasted) / n,
        "wasted_latency_ms": sum(c.latency_ms or 0.0 for c in wasted),
        "total_unique_evidence": sum(c.unique_evidence for c in contributions),
        "total_duplicate_evidence": sum(c.duplicate_evidence for c in contributions),
    }
