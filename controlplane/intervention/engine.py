"""Intervention Engine -- V0. Maps each retry-triggering ``ControlAction``
to an ``InterventionSpec`` describing exactly what should change.
Bounded by construction: it only ever produces one of the three
mechanisms below, each a single bounded step, never a loop itself (the
Decision Engine's ``attempt_number``/``max_attempts`` is what actually
enforces the bound -- see ``controlplane.runtime``).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from controlplane.decision.engine import ControlAction, ControlDecision


class InterventionType(str, Enum):
    RETRIEVE_MORE = "RETRIEVE_MORE"
    CHANGE_MODEL = "CHANGE_MODEL"
    REGENERATE = "REGENERATE"


_ACTION_TO_TYPE = {
    ControlAction.RETRIEVE_MORE: InterventionType.RETRIEVE_MORE,
    ControlAction.CHANGE_MODEL: InterventionType.CHANGE_MODEL,
    ControlAction.REGENERATE: InterventionType.REGENERATE,
}


class InterventionSpec(BaseModel):
    intervention_type: InterventionType
    reason: str
    new_rag_k: int | None = None
    """Set only for RETRIEVE_MORE -- the widened top-k for the retry
    retrieval (V0 mechanism: retrieve more candidates, not full query
    reformulation -- see docs/ALGORITHMS/INTERVENTION_ENGINE.md for why
    LLM-based query expansion was deferred: it would add a model call
    plus latency/cost to every RAG retry, and no evidence yet shows the
    cheaper widened-k mechanism is insufficient)."""
    new_model_role: str | None = None
    """Set for CHANGE_MODEL ("STRONG") and REGENERATE (unchanged role)."""
    triggering_evaluator: str | None = None
    attempt_number: int
    expected_effect: str


class InterventionEngine:
    name = "intervention_v0"

    def __init__(self, retrieve_more_k: int = 10) -> None:
        self._retrieve_more_k = retrieve_more_k

    def plan(self, decision: ControlDecision, current_model_role: str) -> InterventionSpec:
        if not decision.requires_intervention:
            raise ValueError(f"decision.action={decision.action} does not require an intervention")

        intervention_type = _ACTION_TO_TYPE[decision.action]

        if intervention_type is InterventionType.RETRIEVE_MORE:
            return InterventionSpec(
                intervention_type=intervention_type,
                reason=decision.reason,
                new_rag_k=self._retrieve_more_k,
                triggering_evaluator=decision.triggering_evaluator,
                attempt_number=decision.attempt_number,
                expected_effect=f"wider retrieval (k={self._retrieve_more_k}) may surface evidence the first pass missed",
            )
        if intervention_type is InterventionType.CHANGE_MODEL:
            return InterventionSpec(
                intervention_type=intervention_type,
                reason=decision.reason,
                new_model_role="STRONG",
                triggering_evaluator=decision.triggering_evaluator,
                attempt_number=decision.attempt_number,
                expected_effect="a stronger model may produce a more confident, better-reasoned response",
            )
        # REGENERATE
        return InterventionSpec(
            intervention_type=intervention_type,
            reason=decision.reason,
            new_model_role=current_model_role,
            triggering_evaluator=decision.triggering_evaluator,
            attempt_number=decision.attempt_number,
            expected_effect="a fresh generation may not repeat the same contradicted claim",
        )
