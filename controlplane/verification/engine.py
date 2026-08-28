"""Verification Engine -- V0 deterministic baseline. Re-reads the final
round of Evaluation results (after any intervention/replan) and the
Decision Engine's terminal decision, and produces one of four statuses.
Never fabricates VERIFIED -- every status traces to a specific evaluator
result or decision, listed in ``checked_evaluators``/``reason``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from controlplane.decision.engine import ControlAction, ControlDecision
from controlplane.evaluation.evaluators import EvaluationResult


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    REJECTED = "REJECTED"


class VerificationResult(BaseModel):
    status: VerificationStatus
    reason: str
    checked_evaluators: list[str]
    verification_version: str = "verification_v0"


def _find(results: list[EvaluationResult], name: str) -> EvaluationResult | None:
    for r in results:
        if r.evaluator == name:
            return r
    return None


class VerificationEngine:
    name = "verification_v0"

    def verify(self, evaluation_results: list[EvaluationResult], decision: ControlDecision) -> VerificationResult:
        checked = [r.evaluator for r in evaluation_results if r.status.value == "IMPLEMENTED"]

        if decision.action == ControlAction.HUMAN_REVIEW:
            return VerificationResult(
                status=VerificationStatus.REJECTED,
                reason="Decision Engine requires human approval before this can be treated as final",
                checked_evaluators=checked,
            )
        if decision.action == ControlAction.ASK_CLARIFICATION:
            return VerificationResult(
                status=VerificationStatus.NOT_VERIFIED,
                reason="evidence remained insufficient after the retry budget was exhausted; the response asks for clarification rather than asserting a final answer",
                checked_evaluators=checked,
            )

        grounding = _find(evaluation_results, "grounding")
        factuality = _find(evaluation_results, "factuality")
        confidence = _find(evaluation_results, "response_confidence")

        blocking = []
        if grounding and grounding.label == "UNSUPPORTED":
            blocking.append("grounding=UNSUPPORTED")
        if factuality and factuality.label == "CONTRADICTED":
            blocking.append("factuality=CONTRADICTED")
        if confidence and confidence.label == "LOW":
            blocking.append("response_confidence=LOW")
        if blocking:
            return VerificationResult(
                status=VerificationStatus.NOT_VERIFIED, reason="; ".join(blocking), checked_evaluators=checked,
            )

        partial = []
        if grounding and grounding.label == "PARTIALLY_SUPPORTED":
            partial.append("grounding=PARTIALLY_SUPPORTED")
        if factuality and factuality.label == "PARTIALLY_SUPPORTED":
            partial.append("factuality=PARTIALLY_SUPPORTED")
        if partial:
            return VerificationResult(
                status=VerificationStatus.PARTIALLY_VERIFIED, reason="; ".join(partial), checked_evaluators=checked,
            )

        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            reason="no unresolved evaluator concern across grounding/factuality/confidence",
            checked_evaluators=checked,
        )
