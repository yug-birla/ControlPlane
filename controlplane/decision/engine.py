"""Decision Engine -- V0 interpretable policy matrix (bootstrap SS11:
"start with an interpretable baseline... do not reduce the entire
decision to one risk number"). A pure function of already-computed
signals (Evaluation layer results, Risk Profile, the original Model
Router decision, and the current attempt number) -- no model call, no
DB access; persistence happens in ``controlplane.runtime``, not here.

Bounded by construction: ``attempt_number`` vs. ``max_attempts`` is the
only state this needs to guarantee termination (bootstrap SS19: "bounded
self-healing... do not retry forever") -- once the budget is exhausted,
every branch below resolves to a terminal action (CONTINUE, ASK_CLARIFICATION,
or HUMAN_REVIEW), never another retry-triggering action.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from controlplane.evaluation.evaluators import EvaluationResult
from controlplane.risk.profile import RiskProfile
from controlplane.routing.model_router import ModelRouteDecision


class ControlAction(str, Enum):
    CONTINUE = "CONTINUE"
    VERIFY = "VERIFY"
    RETRIEVE_MORE = "RETRIEVE_MORE"
    CHANGE_MODEL = "CHANGE_MODEL"
    REGENERATE = "REGENERATE"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    ABSTAIN = "ABSTAIN"


_RETRY_ACTIONS = {ControlAction.RETRIEVE_MORE, ControlAction.CHANGE_MODEL, ControlAction.REGENERATE}


class ControlDecision(BaseModel):
    action: ControlAction
    reason: str
    triggering_evaluator: str | None = None
    attempt_number: int
    can_retry: bool
    decision_version: str = "policy_matrix_v0"

    @property
    def requires_intervention(self) -> bool:
        return self.action in _RETRY_ACTIONS


def _find(results: list[EvaluationResult], name: str) -> EvaluationResult | None:
    for r in results:
        if r.evaluator == name:
            return r
    return None


class DecisionEngine:
    name = "policy_matrix_v0"

    def __init__(self, max_attempts: int = 2) -> None:
        self._max_attempts = max_attempts

    def decide(
        self,
        evaluation_results: list[EvaluationResult],
        risk: RiskProfile,
        model_decision: ModelRouteDecision,
        attempt_number: int = 1,
    ) -> ControlDecision:
        can_retry = attempt_number < self._max_attempts

        action_risk = _find(evaluation_results, "action_risk")
        grounding = _find(evaluation_results, "grounding")
        factuality = _find(evaluation_results, "factuality")
        confidence = _find(evaluation_results, "response_confidence")

        # Hard constraint, checked first and unconditionally: a high-risk
        # action always needs a human, retry budget or not -- this is not
        # a "quality" concern the retry loop can fix.
        if action_risk and action_risk.label in ("HIGH_RISK", "CRITICAL"):
            return ControlDecision(
                action=ControlAction.HUMAN_REVIEW,
                reason=f"action_risk={action_risk.label} requires human sign-off regardless of evaluation outcome",
                triggering_evaluator="action_risk",
                attempt_number=attempt_number,
                can_retry=can_retry,
            )

        if grounding and grounding.label == "UNSUPPORTED":
            if can_retry:
                return ControlDecision(
                    action=ControlAction.RETRIEVE_MORE,
                    reason=f"grounding=UNSUPPORTED (coverage={grounding.score:.2f}) -- retrieved evidence does not support the answer",
                    triggering_evaluator="grounding",
                    attempt_number=attempt_number,
                    can_retry=can_retry,
                )
            return ControlDecision(
                action=ControlAction.ASK_CLARIFICATION,
                reason="grounding remained UNSUPPORTED after the retry budget was exhausted",
                triggering_evaluator="grounding",
                attempt_number=attempt_number,
                can_retry=False,
            )

        if factuality and factuality.label == "CONTRADICTED":
            if can_retry:
                return ControlDecision(
                    action=ControlAction.REGENERATE,
                    reason="factuality=CONTRADICTED -- the answer's numeric claims do not match the SQL evidence",
                    triggering_evaluator="factuality",
                    attempt_number=attempt_number,
                    can_retry=can_retry,
                )
            return ControlDecision(
                action=ControlAction.HUMAN_REVIEW,
                reason="factuality remained CONTRADICTED after the retry budget was exhausted",
                triggering_evaluator="factuality",
                attempt_number=attempt_number,
                can_retry=False,
            )

        if confidence and confidence.label == "LOW" and can_retry and model_decision.model_role == "FAST":
            return ControlDecision(
                action=ControlAction.CHANGE_MODEL,
                reason=f"response_confidence=LOW ({confidence.rationale}) on the fast model -- escalating",
                triggering_evaluator="response_confidence",
                attempt_number=attempt_number,
                can_retry=can_retry,
            )

        if grounding and grounding.label == "PARTIALLY_SUPPORTED":
            return ControlDecision(
                action=ControlAction.VERIFY,
                reason=f"grounding=PARTIALLY_SUPPORTED (coverage={grounding.score:.2f}) -- accept only if verification passes",
                triggering_evaluator="grounding",
                attempt_number=attempt_number,
                can_retry=can_retry,
            )

        if model_decision.require_verification:
            return ControlDecision(
                action=ControlAction.VERIFY,
                reason="Model Router flagged require_verification=True for this route",
                attempt_number=attempt_number,
                can_retry=can_retry,
            )

        return ControlDecision(
            action=ControlAction.CONTINUE,
            reason="no evaluator flagged a concern requiring intervention",
            attempt_number=attempt_number,
            can_retry=can_retry,
        )
