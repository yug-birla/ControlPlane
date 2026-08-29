"""Adaptive compute allocation: spend more only when it is justified.

Milestone 11 (§11-§16, §20). The stated objective:

    "Select the least expensive / least complex model-compute path that
     can reliably satisfy the current task under current risk and quality
     constraints."

WHAT THIS REPLACES: the Model Router picks a role (FAST/STRONG) *before*
execution, from the query profile alone. That is a pre-execution
hypothesis and it stays. This module makes the *post-execution* decision:
given what actually came back, is more compute warranted, and if so
which kind?

THREE OUTCOMES, in increasing cost:

    STOP           the result is good enough; spend nothing more
    SELF_REFINE    same model, one more bounded pass with the evaluator's
                   own findings as feedback
    ESCALATE       a different, stronger model

WHY SELF_REFINE IS PREFERRED OVER ESCALATE HERE -- AND WHY THAT IS AN
EVIDENCE DECISION, NOT A STYLE ONE:

On this project, escalation is currently *not* supported by evidence. The
measured tier comparison (``docs/EVALUATION/MODEL_TIER_RESULTS.md``)
found the larger model scoring **lower** (0.800 vs 0.900) at ~2.5x the
per-token cost. A router that escalated on every quality concern would
reliably spend more to get less. So escalation must clear an evidence
bar (``model_performance.escalation_is_evidence_backed``), and when it
does not, the cheaper self-refinement path is used instead.

If a future measurement shows the stronger model genuinely wins, the same
function will start returning True and escalation will begin firing -- no
code change, because the policy reads evidence rather than encoding a
belief about which model is better.

HARD CONSTRAINTS ARE NOT NEGOTIABLE BY COMPUTE. A high-risk action or a
detected injection is not a "spend more tokens" problem; those already
terminate at HUMAN_REVIEW/BLOCK in the Decision Engine and this module
never overrides that. It only allocates compute for *quality* concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ComputeAction(str, Enum):
    STOP = "STOP"
    SELF_REFINE = "SELF_REFINE"
    ESCALATE = "ESCALATE"


# Evaluators whose failure indicates a QUALITY problem that more compute
# could plausibly fix. Safety/risk evaluators are deliberately absent:
# those are hard constraints handled upstream, not compute problems.
_QUALITY_EVALUATORS = {"grounding", "factuality", "reasoning", "response_confidence"}

# Bounded, per the directive's explicit instruction not to create
# unbounded loops. One refinement pass is the budget: a second pass on a
# 1.5B model has not been shown to help, and would double latency on the
# already-slow CPU path.
MAX_REFINEMENT_PASSES = 1


@dataclass
class ComputeDecision:
    action: ComputeAction
    reason: str
    target_model_role: str | None = None
    triggering_evaluators: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "target_model_role": self.target_model_role,
            "triggering_evaluators": self.triggering_evaluators,
            "evidence": self.evidence,
        }


class AdaptiveComputePolicy:
    name = "adaptive_compute_v1"

    def __init__(self, max_refinement_passes: int = MAX_REFINEMENT_PASSES) -> None:
        self._max_refinement_passes = max_refinement_passes

    def decide(
        self,
        *,
        quality_concerns: list[str],
        current_role: str,
        refinement_passes_used: int,
        risk_severity: str,
        escalation_supported: bool,
        escalation_reason: str = "",
        budget_exhausted: bool = False,
    ) -> ComputeDecision:
        """Decide whether to spend more compute, and on what.

        ``quality_concerns`` are the names of evaluators that flagged a
        quality problem. ``escalation_supported`` comes from observed
        model performance, not from an assumption about model size.
        """
        concerns = [e for e in quality_concerns if e in _QUALITY_EVALUATORS]

        if not concerns:
            return ComputeDecision(
                action=ComputeAction.STOP,
                reason="no quality evaluator raised a concern -- additional compute would "
                       "not improve a result that is already acceptable",
            )

        if budget_exhausted:
            return ComputeDecision(
                action=ComputeAction.STOP,
                reason="quality concerns remain but the attempt budget is exhausted; "
                       "the control loop resolves this by abstaining or asking for "
                       "clarification rather than spending unbounded compute",
                triggering_evaluators=concerns,
            )

        # A strong model that is already failing is unlikely to be fixed
        # by a second pass of itself, and there is nothing above it to
        # escalate to. Stop and let the control loop's own
        # abstain/clarify path handle it -- this is the directive's
        # "do not add unnecessary self-refinement to the strong path".
        if current_role == "STRONG":
            return ComputeDecision(
                action=ComputeAction.STOP,
                reason="already on the strongest configured path; further self-refinement "
                       "on the same model is not evidence-backed and there is no stronger "
                       "model to escalate to",
                triggering_evaluators=concerns,
            )

        if escalation_supported:
            return ComputeDecision(
                action=ComputeAction.ESCALATE,
                reason=f"quality concerns {concerns} and observed history supports "
                       f"escalation: {escalation_reason}",
                target_model_role="STRONG",
                triggering_evaluators=concerns,
                evidence={"escalation_reason": escalation_reason},
            )

        if refinement_passes_used < self._max_refinement_passes:
            return ComputeDecision(
                action=ComputeAction.SELF_REFINE,
                reason=f"quality concerns {concerns}; escalation is NOT evidence-backed "
                       f"({escalation_reason}), so the cheaper same-model refinement pass "
                       "is preferred over spending more compute for no measured gain",
                target_model_role=current_role,
                triggering_evaluators=concerns,
                evidence={"escalation_reason": escalation_reason,
                          "refinement_passes_used": refinement_passes_used},
            )

        return ComputeDecision(
            action=ComputeAction.STOP,
            reason=f"refinement budget exhausted ({refinement_passes_used}/"
                   f"{self._max_refinement_passes}) and escalation is not evidence-backed",
            triggering_evaluators=concerns,
        )


def build_refinement_prompt(*, original_prompt: str, previous_answer: str, concerns: list[str]) -> str:
    """One bounded self-refinement pass, using the evaluator's own findings.

    The feedback is the *evaluator's* structured verdict, not the model's
    own self-assessment: asking a 1.5B model to critique itself tends to
    produce agreement rather than correction, whereas the grounding and
    factuality evaluators are independent of it.

    No hidden chain-of-thought is requested or stored -- the model is
    asked for a corrected answer, not for its reasoning.
    """
    issues = ", ".join(concerns) or "quality"
    return (
        f"{original_prompt}\n\n"
        f"A previous attempt produced this answer:\n{previous_answer}\n\n"
        f"An independent check found problems with it ({issues}). "
        "Write a corrected answer that is fully supported by the provided context. "
        "If the context does not contain the answer, say so explicitly instead of guessing. "
        "Give only the corrected answer."
    )
