"""Judge-backed evaluators -- implement the same ``Evaluator`` interface
as the deterministic evaluators in ``controlplane.evaluation.evaluators``
(bootstrap SS23: "a replaceable strategy," proven here by literally being
swappable into an ``EvaluationSuite``), but are NOT included in
``EvaluationSuite()``'s default list used by the live runtime.

Why: measured Local Judge latency is ~30-90s per call on this CPU-only
machine (docs/EVALUATION/EVALUATOR_RESULTS.md) -- acceptable for the
bootstrap's "NO-GPU DEMONSTRATION ENVIRONMENT" policy in an offline
calibration/comparison context, but not for a live per-request budget
that the rest of the Evaluation Suite keeps under ~100ms. Remote Judge
(Gemini) is fast (~1-2s) but is explicitly never the default route
either (quota, and bootstrap SS14: "do not send every response to
Gemini"). These classes exist, are tested, and are used by
``controlplane/experiments/evaluate_judge_calibration.py`` -- a real,
working, swappable component, just not defaulted into the hot path.
"""

from __future__ import annotations

from controlplane.evaluation.evaluators import EvaluationContext, EvaluationResult, Evaluator
from controlplane.judge.schema import JudgeStatus

_STATUS_MAP = {
    JudgeStatus.IMPLEMENTED: "IMPLEMENTED",
    JudgeStatus.PARSE_FAILED: "NOT_IMPLEMENTED",
    JudgeStatus.ERROR: "NOT_IMPLEMENTED",
}

_NEGATIVE_LABELS = {"UNSUPPORTED", "POOR", "INCONSISTENT", "UNSAFE"}
_PARTIAL_LABELS = {"PARTIALLY_SUPPORTED", "ACCEPTABLE", "MINOR_ISSUE", "CONCERNING"}


class JudgeBackedEvaluator(Evaluator):
    """Wraps any object exposing ``.evaluate(task, *, query, answer,
    evidence) -> JudgeResult`` (``LocalJudge`` or ``RemoteJudge``) as a
    standard ``Evaluator``."""

    def __init__(self, judge, task: str) -> None:
        self._judge = judge
        self._task = task
        self.name = f"judge_{task}_{getattr(judge, 'name', 'unknown')}"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if not ctx.answer:
            return EvaluationResult(
                evaluator=self.name, status="NOT_IMPLEMENTED", rationale="no answer to judge",
            )
        result = self._judge.evaluate(
            self._task, query=ctx.query, answer=ctx.answer, evidence=ctx.evidence_texts or None,
        )
        if result.label in _NEGATIVE_LABELS:
            signal = "FLAG_FOR_REVIEW"
        elif result.label in _PARTIAL_LABELS:
            signal = "FLAG_FOR_REVIEW"
        elif result.label is not None:
            signal = "OK"
        else:
            signal = None

        return EvaluationResult(
            evaluator=self.name,
            status=_STATUS_MAP[result.status],
            label=result.label,
            score=result.score,
            evidence={"issues": result.issues, "judge_model": result.model, "judge_latency_ms": result.latency_ms},
            rationale=result.rationale or f"judge status={result.status.value}",
            recommended_signal=signal,
        )
