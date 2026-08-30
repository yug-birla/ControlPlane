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
        rag_adequacy = _find(evaluation_results, "rag_adequacy")
        agent_governance = _find(evaluation_results, "agent_governance")
        prompt_injection = _find(evaluation_results, "prompt_injection")

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

        # Hard constraint: a detected prompt-injection pattern is a
        # security concern, never something a retry/regenerate can
        # resolve (the malicious instruction is in the query itself).
        if prompt_injection and prompt_injection.label == "INJECTION_PATTERN_DETECTED":
            # The reason must describe HOW it was detected, not assume a
            # keyword match. The detector has two layers: a deterministic
            # phrase list and an embedding k-NN layer, and the semantic
            # layer populates `evidence` while leaving `issues` empty.
            # Reading `issues` unconditionally printed
            # "detected known injection phrasing: []" for exactly the
            # cases the semantic layer caught -- a message that looks
            # broken and understates the system, on the one screen where
            # a reviewer is deciding whether to trust it.
            evidence = prompt_injection.evidence or {}
            nearest = evidence.get("nearest_reference_example")
            if prompt_injection.issues:
                detail = f"matched phrasing: {prompt_injection.issues}"
            elif nearest:
                method = evidence.get("detection_method", "semantic")
                detail = f"{method} match, nearest known example: {nearest!r}"
            else:
                detail = prompt_injection.rationale or "no detail recorded"
            return ControlDecision(
                action=ControlAction.HUMAN_REVIEW,
                reason=f"prompt_injection -- {detail}",
                triggering_evaluator="prompt_injection",
                attempt_number=attempt_number,
                can_retry=can_retry,
            )

        # Hard constraint: a BLOCKed or human-review-pending agent tool
        # proposal is never something a retry can fix (the tool simply
        # didn't run) -- found via a real end-to-end trace where the
        # query-level risk (MEDIUM_RISK) under-assessed a specific
        # HIGH_RISK tool proposal, and nothing downstream reflected that
        # the requested action had actually been withheld: Trust reported
        # HIGH despite the response not doing what was asked.
        if agent_governance and agent_governance.label in ("BLOCK", "HUMAN_REVIEW"):
            return ControlDecision(
                action=ControlAction.HUMAN_REVIEW,
                reason=f"agent_governance={agent_governance.label} -- the proposed tool call was not executed and requires human sign-off",
                triggering_evaluator="agent_governance",
                attempt_number=attempt_number,
                can_retry=can_retry,
            )

        # CONFLICTING is a distinct failure from UNSUPPORTED grounding:
        # the evidence disagrees with ITSELF, not with the answer. A
        # RETRIEVE_MORE retry can still legitimately help here (a wider
        # candidate set might surface a resolving/authoritative document
        # not in the first pass) -- but bootstrap SS29 explicitly warns
        # against "INSUFFICIENT -> always retry" as the *only* mechanism,
        # so once the retry budget is spent this asks for clarification
        # rather than silently picking one of the conflicting values.
        if rag_adequacy and rag_adequacy.label == "CONFLICTING":
            if can_retry:
                return ControlDecision(
                    action=ControlAction.RETRIEVE_MORE,
                    reason="rag_adequacy=CONFLICTING -- retrieved evidence disagrees with itself; a wider retrieval may surface an authoritative source",
                    triggering_evaluator="rag_adequacy",
                    attempt_number=attempt_number,
                    can_retry=can_retry,
                )
            return ControlDecision(
                action=ControlAction.ASK_CLARIFICATION,
                reason="rag_adequacy remained CONFLICTING after the retry budget was exhausted -- asking rather than silently picking one of the conflicting values",
                triggering_evaluator="rag_adequacy",
                attempt_number=attempt_number,
                can_retry=False,
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
