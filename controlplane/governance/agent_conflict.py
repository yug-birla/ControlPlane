"""When two agents disagree, do not quietly pick one.

§15. Two gatherers reading different sources can return incompatible
answers to the same question -- a policy document saying the meal limit
is $75 and a database row saying $100. Until now nothing looked. Both
results went into the merge node, generation saw both, and whichever the
model happened to favour became the answer, with no record that a
disagreement had occurred at all.

Silently choosing is the failure being guarded against, and the obvious
tie-breaks are all forms of it: first agent, last agent, the one with
more evidence, the one whose text is longer. None of those is a reason
to believe one number over another.

WHAT THIS DOES. It detects the disagreement and classifies how it can be
settled, reusing the numeric-claim extraction already built and measured
for the reasoning evaluator rather than inventing a second notion of
"same claim":

    SOURCE_AUTHORITY   one agent read a source that is authoritative for
                       this kind of fact and the other did not
    UNRESOLVED         no defensible basis for preferring either

WHY UNRESOLVED IS A RESULT AND NOT A FAILURE. This runtime already takes
the position that conflicting evidence is different from missing
evidence, and that the right response is to disclose rather than pick a
side (`Runtime._replan_capability`, the Milestone 6 conflicting-evidence
scenario). An unresolved conflict is a real finding: it tells the
decision engine to surface the disagreement or ask for clarification,
which is a better outcome than a confident answer drawn from a coin
flip.

WHAT COUNTS AS AUTHORITY. Only one narrow, stated rule: the enterprise
database is authoritative for figures it stores, and a document that
quotes such a figure is a copy that can be stale. It is deliberately not
a general ranking of sources, because there is no measured basis for one
here -- and an invented hierarchy applied confidently would be exactly
the silent choosing this module exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from controlplane.evaluation.reasoning_consistency import (
    extract_numeric_claims,
    split_clauses,
)
from controlplane.governance.handoff import evidence_items

SUBJECT_OVERLAP_THRESHOLD = 0.34
"""How much of two claims' subject wording must coincide before they are
treated as claims about the same thing. Two numbers in the same document
are usually about different things; requiring real overlap is what stops
every pair of figures becoming a conflict."""

# The single authority rule, stated rather than assumed.
_AUTHORITATIVE_FOR_FIGURES = "SQL"


class ConflictResolution(str, Enum):
    SOURCE_AUTHORITY = "SOURCE_AUTHORITY"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class AgentConflict:
    subject: str
    left_agent: str
    right_agent: str
    left_value: float
    right_value: float
    left_source: str | None
    right_source: str | None
    unit: str
    resolution: ConflictResolution
    preferred_agent: str | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "left_agent": self.left_agent,
            "right_agent": self.right_agent,
            "left_value": self.left_value,
            "right_value": self.right_value,
            "left_source": self.left_source,
            "right_source": self.right_source,
            "unit": self.unit,
            "resolution": self.resolution.value,
            "preferred_agent": self.preferred_agent,
            "reason": self.reason,
        }


def _claims_for(result: dict) -> list:
    claims = []
    for item in evidence_items(result):
        text = item.get("text") or item.get("content") or str(item) if isinstance(item, dict) else str(item)
        for clause in split_clauses(text):
            claims.extend(extract_numeric_claims(clause))
    return claims


def _same_subject(left, right) -> bool:
    if left.unit != right.unit:
        return False
    if not left.subject or not right.subject:
        return False
    shared = left.subject & right.subject
    smaller = min(len(left.subject), len(right.subject))
    return len(shared) / smaller >= SUBJECT_OVERLAP_THRESHOLD


def _resolve(left_source, right_source, left_agent, right_agent):
    """The only defensible preference available here, or none."""
    if left_source == _AUTHORITATIVE_FOR_FIGURES and right_source != _AUTHORITATIVE_FOR_FIGURES:
        return ConflictResolution.SOURCE_AUTHORITY, left_agent, (
            f"{left_agent} read the enterprise database, which stores this figure; "
            f"{right_agent} read a document that can quote a stale copy of it"
        )
    if right_source == _AUTHORITATIVE_FOR_FIGURES and left_source != _AUTHORITATIVE_FOR_FIGURES:
        return ConflictResolution.SOURCE_AUTHORITY, right_agent, (
            f"{right_agent} read the enterprise database, which stores this figure; "
            f"{left_agent} read a document that can quote a stale copy of it"
        )
    return ConflictResolution.UNRESOLVED, None, (
        "both agents read sources of the same kind, so there is no basis for "
        "preferring either value -- the disagreement is surfaced rather than settled"
    )


def detect_conflicts(agent_results: list[tuple[str, dict]]) -> list[AgentConflict]:
    """Cross-agent numeric disagreements about the same subject.

    Only across DIFFERENT agents: two figures inside one agent's evidence
    are that source's own business, and the reasoning evaluator already
    checks an answer for internal contradiction.
    """
    per_agent = [
        (agent_id, result.get("serves_capability"), _claims_for(result))
        for agent_id, result in agent_results
    ]

    conflicts: list[AgentConflict] = []
    for i, (left_agent, left_source, left_claims) in enumerate(per_agent):
        for right_agent, right_source, right_claims in per_agent[i + 1:]:
            for left in left_claims:
                for right in right_claims:
                    if left.value == right.value or not _same_subject(left, right):
                        continue
                    resolution, preferred, reason = _resolve(
                        left_source, right_source, left_agent, right_agent
                    )
                    conflicts.append(AgentConflict(
                        subject=" ".join(sorted(left.subject & right.subject)),
                        left_agent=left_agent, right_agent=right_agent,
                        left_value=left.value, right_value=right.value,
                        left_source=left_source, right_source=right_source,
                        unit=left.unit, resolution=resolution,
                        preferred_agent=preferred, reason=reason,
                    ))
    return conflicts


def summarise(conflicts: list[AgentConflict]) -> dict:
    unresolved = [c for c in conflicts if c.resolution is ConflictResolution.UNRESOLVED]
    return {
        "conflict_count": len(conflicts),
        "unresolved_count": len(unresolved),
        "resolved_by_authority_count": len(conflicts) - len(unresolved),
        # An unresolved cross-agent conflict is a reason to disclose or
        # ask, never a reason to answer confidently from one side.
        "requires_disclosure": bool(unresolved),
        "conflicts": [c.to_dict() for c in conflicts],
    }
