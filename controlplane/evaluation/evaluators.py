"""Evaluator interfaces + the evaluators implemented so far:

- Privacy/PII, Action Risk, Safety: deterministic passthroughs of
  already-computed Risk Profiler signals (never a second independent
  detector -- bootstrap SS3's "one cheap inference" principle applies to
  evaluators too).
- Grounding: lexical claim/evidence overlap -- a real, if simple,
  baseline per bootstrap SS24 ("extract only useful mechanisms" from
  SelfCheckGPT/RAGTruth, not reproduce them).
- Factuality: deterministic numeric-claim checking against SQL evidence
  when it exists, NOT_APPLICABLE otherwise (bootstrap SS14).
- Response Confidence: a real, deterministic *surface* signal (hedging
  language + answer length) used by the Decision Engine as an escalation
  trigger -- not a substitute for true model-calibrated confidence.

Reasoning: a narrow deterministic self-contradiction check (real, but not
general logical-validity checking -- see ``ReasoningEvaluator``'s
docstring). Bias is declared but not implemented as a single-context
``Evaluator`` (``NotImplementedEvaluator("bias")``) -- it is inherently
comparative/paired, so it lives as a standalone module,
``controlplane.evaluation.bias``, instead. Per bootstrap SS46 ("Never
return fabricated... If something is heuristic, mark it as heuristic."),
nothing here reports a fabricated score. See
docs/ALGORITHMS/EVALUATION_LAYER.md for the full per-evaluator rationale.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

from controlplane.query_intelligence.fingerprint import QueryFingerprint, Sensitivity
from controlplane.risk.profile import RiskProfile


class EvaluationStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class EvaluationResult(BaseModel):
    evaluator: str
    status: EvaluationStatus
    label: str | None = None
    score: float | None = None
    confidence: float | None = None
    evidence: dict = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    rationale: str
    recommended_signal: str | None = None
    """A signal for a future Decision Engine/Intervention Engine to
    consume -- e.g. "OK"/"FLAG_FOR_REVIEW" -- never itself an action.
    Layer 14-15 don't exist yet, so nothing currently reads this field;
    it is recorded for when they do."""


@dataclass
class EvaluationContext:
    query: str
    answer: str | None
    evidence_texts: list[str] = field(default_factory=list)
    sql_rows: list[dict] = field(default_factory=list)
    """Structured rows from the SQL capability, when it ran -- distinct
    from ``evidence_texts`` (RAG's unstructured text) because numeric
    claims are checked against structured values, not lexical overlap
    (see ``FactualityEvaluator``)."""
    rag_adequacy: str | None = None
    """The RAG node's own ``controlplane.rag.adequacy.AdequacyLabel``
    (SUFFICIENT/PARTIALLY_SUFFICIENT/INSUFFICIENT/CONFLICTING), passed
    through so the Decision Engine can react to CONFLICTING specifically
    -- distinct from ``GroundingEvaluator``'s answer-vs-evidence overlap,
    this is about the evidence disagreeing with ITSELF, which retrieving
    more of the same evidence or regenerating from it cannot fix the same
    way an UNSUPPORTED grounding failure can."""
    fingerprint: QueryFingerprint | None = None
    risk: RiskProfile | None = None


class Evaluator(ABC):
    name: str

    @abstractmethod
    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult: ...


_SENSITIVITY_SCORE = {
    Sensitivity.NONE: 0.0,
    Sensitivity.POTENTIAL_PII: 0.33,
    Sensitivity.PII_EXPOSURE: 0.66,
    Sensitivity.SENSITIVE_DATA_EXPOSURE: 1.0,
}


class PrivacyPIIEvaluator(Evaluator):
    """Deterministic passthrough of the Query Profiler's already-computed
    ``sensitivity`` field -- deliberately not a second, independent PII
    detector (bootstrap SS3's "one cheap inference, not N independent
    ones" principle applies to evaluators too)."""

    name = "privacy_pii"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.fingerprint is None:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.NOT_IMPLEMENTED,
                rationale="no QueryFingerprint available in this context",
            )
        sensitivity = ctx.fingerprint.sensitivity
        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label=sensitivity.value,
            score=_SENSITIVITY_SCORE[sensitivity],
            confidence=1.0 if sensitivity != Sensitivity.NONE else None,
            rationale=f"derived directly from Query Profiler sensitivity={sensitivity.value}, not re-computed",
            recommended_signal="FLAG_FOR_REVIEW" if sensitivity != Sensitivity.NONE else "OK",
        )


class ActionRiskEvaluator(Evaluator):
    """Deterministic passthrough of the Risk Profiler's ``action``
    dimension + overall severity."""

    name = "action_risk"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.risk is None:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.NOT_IMPLEMENTED,
                rationale="no RiskProfile available in this context",
            )
        action_severity = ctx.risk.risk_dimensions.get("action")
        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label=ctx.risk.severity.value,
            evidence={"action_dimension": action_severity.value if action_severity else None, "trigger_signals": ctx.risk.trigger_signals},
            rationale=f"derived directly from Risk Profiler severity={ctx.risk.severity.value}",
            recommended_signal="FLAG_FOR_REVIEW" if ctx.risk.severity.value in ("HIGH_RISK", "CRITICAL") else "OK",
        )


class RAGAdequacyPassthroughEvaluator(Evaluator):
    """Deterministic passthrough of ``EvaluationContext.rag_adequacy`` --
    same pattern as Privacy/ActionRisk/Safety (bootstrap SS3: "one cheap
    inference, not N independent ones"). Exists mainly so the Decision
    Engine has a normal ``EvaluationResult`` to key off of for CONFLICTING
    evidence (bootstrap SS29), rather than reaching around the Evaluation
    layer into raw graph node output."""

    name = "rag_adequacy"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.rag_adequacy is None:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.IMPLEMENTED, label="NOT_APPLICABLE",
                rationale="no RAG node ran for this request",
            )
        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label=ctx.rag_adequacy,
            rationale=f"passthrough of the RAG capability's own adequacy assessment: {ctx.rag_adequacy}",
            recommended_signal="FLAG_FOR_REVIEW" if ctx.rag_adequacy in ("INSUFFICIENT", "CONFLICTING") else "OK",
        )


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "for", "in", "on", "at", "and", "or", "our",
    "we", "with", "this", "that", "it", "as", "be", "has", "have", "had", "by", "from", "about",
}


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


class GroundingEvaluator(Evaluator):
    """Claim/evidence support via lexical overlap between the answer and
    the retrieved evidence text -- a real, deterministic baseline, not a
    reproduction of SelfCheckGPT/RAGTruth (bootstrap SS24: "extract only
    useful mechanisms"). Only meaningful when RAG evidence exists;
    otherwise reports NOT_APPLICABLE (not a fabricated score) --
    see docs/ALGORITHMS/EVALUATION_LAYER.md."""

    name = "grounding"

    def __init__(self, supported_threshold: float = 0.5, partial_threshold: float = 0.2) -> None:
        self._supported = supported_threshold
        self._partial = partial_threshold

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if not ctx.evidence_texts:
            return EvaluationResult(
                evaluator=self.name,
                status=EvaluationStatus.IMPLEMENTED,
                label="NOT_APPLICABLE",
                rationale="no evidence available for this response (non-RAG capability path)",
            )
        if not ctx.answer:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.IMPLEMENTED, label="NOT_APPLICABLE",
                rationale="no answer to check groundedness of",
            )

        answer_terms = _content_tokens(ctx.answer)
        if not answer_terms:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.IMPLEMENTED, label="NOT_APPLICABLE",
                rationale="answer had no scorable content terms",
            )

        evidence_terms: set[str] = set()
        for text in ctx.evidence_texts:
            evidence_terms |= _content_tokens(text)

        overlap = answer_terms & evidence_terms
        coverage = len(overlap) / len(answer_terms)

        if coverage >= self._supported:
            label, signal = "SUPPORTED", "OK"
        elif coverage >= self._partial:
            label, signal = "PARTIALLY_SUPPORTED", "FLAG_FOR_REVIEW"
        else:
            label, signal = "UNSUPPORTED", "FLAG_FOR_REVIEW"

        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label=label,
            score=coverage,
            evidence={"overlapping_terms": sorted(overlap)[:20]},
            rationale=f"{len(overlap)}/{len(answer_terms)} answer content terms ({coverage:.2f}) appear in the retrieved evidence",
            recommended_signal=signal,
        )


class SafetyEvaluator(Evaluator):
    """Deterministic passthrough of the Risk Profiler's ``safety``
    dimension -- same pattern as Privacy/ActionRisk. Does not claim
    universal safety coverage (bootstrap SS16): it only reports what the
    existing safety keyword triggers already detected."""

    name = "safety"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.risk is None:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.NOT_IMPLEMENTED,
                rationale="no RiskProfile available in this context",
            )
        safety_severity = ctx.risk.risk_dimensions.get("safety")
        label = safety_severity.value if safety_severity else "NO_ACTION"
        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label=label,
            rationale=f"derived directly from Risk Profiler safety dimension={label} -- keyword-triggered only, not a general unsafe-intent classifier",
            recommended_signal="FLAG_FOR_REVIEW" if label not in ("NO_ACTION", "LOW_RISK") else "OK",
        )


_HEDGING_PHRASES = (
    "i'm not sure", "i am not sure", "i don't know", "i do not know", "it's unclear", "it is unclear",
    "cannot determine", "unable to determine", "not enough information", "i cannot confirm",
    "i don't have", "i do not have access", "as an ai", "i cannot provide",
)


class ResponseConfidenceEvaluator(Evaluator):
    """A real, deterministic *surface* confidence signal -- hedging
    language + answer length relative to query complexity -- used by the
    Decision Engine as a proxy for "the fast model's response looks
    uncertain" (bootstrap's Model Escalation scenario, SS23). Not a
    substitute for the model's own calibrated confidence (Groq/Gemini do
    not return one by default) and not a claim about correctness --
    purely a signal about how the response *presents* itself."""

    name = "response_confidence"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if not ctx.answer:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.NOT_IMPLEMENTED, rationale="no answer to assess",
            )
        answer_lower = ctx.answer.lower()
        hedges = [p for p in _HEDGING_PHRASES if p in answer_lower]
        word_count = len(ctx.answer.split())

        if hedges:
            label = "LOW"
        elif word_count < 4:
            label = "LOW"
        elif word_count < 10:
            label = "MEDIUM"
        else:
            label = "HIGH"

        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label=label,
            evidence={"hedging_phrases_found": hedges, "word_count": word_count},
            rationale=(
                f"hedging phrases found: {hedges}" if hedges else f"no hedging language; word_count={word_count}"
            ),
            recommended_signal="FLAG_FOR_REVIEW" if label == "LOW" else "OK",
        )


_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _normalized_numbers(text: str) -> set[float]:
    numbers = set()
    for raw in _NUMBER_RE.findall(text):
        cleaned = raw.replace(",", "")
        try:
            numbers.add(round(float(cleaned), 2))
        except ValueError:
            continue
    return numbers


class FactualityEvaluator(Evaluator):
    """Deterministic ground-truth checking for numeric claims against
    structured (SQL) AND text (RAG) evidence (bootstrap SS14: "For
    answers with deterministic ground truth: compare to ground truth")
    -- NOT_APPLICABLE (not a fabricated score) whenever no evidence
    exists to check against. Deliberately narrow: this checks whether
    numbers mentioned in the answer appear in the retrieved evidence, not
    general claim-level factuality (see docs/ALGORITHMS/EVALUATION_LAYER.md
    for why a full claim-extraction pipeline was not attempted this
    milestone).

    Checks *both* evidence sources, not SQL alone -- found via manual
    validation (a multi-source SQL+RAG query) that checking SQL rows
    only made every RAG-sourced number look "CONTRADICTED" simply for
    not being SQL data, which would have wrongly triggered a REGENERATE
    intervention on a correct, RAG-grounded answer."""

    name = "factuality"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if (not ctx.sql_rows and not ctx.evidence_texts) or not ctx.answer:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.IMPLEMENTED, label="NOT_APPLICABLE",
                rationale="no SQL or RAG evidence available to check numeric claims against",
            )

        answer_numbers = _normalized_numbers(ctx.answer)
        if not answer_numbers:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.IMPLEMENTED, label="NOT_APPLICABLE",
                rationale="answer contains no numeric claims to check",
            )

        evidence_numbers: set[float] = set()
        for row in ctx.sql_rows:
            for value in row.values():
                if isinstance(value, (int, float)):
                    evidence_numbers.add(round(float(value), 2))
                elif isinstance(value, str):
                    evidence_numbers |= _normalized_numbers(value)
        for text in ctx.evidence_texts:
            evidence_numbers |= _normalized_numbers(text)

        matched = answer_numbers & evidence_numbers
        unmatched = answer_numbers - evidence_numbers

        if not unmatched:
            label, signal = "SUPPORTED", "OK"
        elif matched:
            label, signal = "PARTIALLY_SUPPORTED", "FLAG_FOR_REVIEW"
        else:
            label, signal = "CONTRADICTED", "FLAG_FOR_REVIEW"

        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label=label,
            evidence={"answer_numbers": sorted(answer_numbers), "matched": sorted(matched), "unmatched": sorted(unmatched)},
            rationale=f"{len(matched)}/{len(answer_numbers)} numeric claims in the answer match a value in the SQL evidence",
            recommended_signal=signal,
        )


_CONTRADICTION_PAIRS = [
    ("is allowed", "is not allowed"), ("is required", "is not required"),
    ("is permitted", "is not permitted"), ("can be", "cannot be"), ("must", "must not"),
    ("is mandatory", "is optional"), ("is eligible", "is not eligible"),
]


class ReasoningEvaluator(Evaluator):
    """Deterministic self-contradiction check -- the only reasoning-quality
    signal available without either a multi-step trace (single-shot
    generation doesn't produce one to check "verifiable calculations"/
    "constraint satisfaction" against, per bootstrap SS18) or a live judge
    call (measured 30-90s/call on this CPU-only machine -- too slow for
    the live per-request suite, see docs/ALGORITHMS/EVALUATION_LAYER.md).

    Deliberately reports ``NO_CONTRADICTION_DETECTED``, not "CONSISTENT"
    or "SOUND" -- this checks for one narrow failure pattern (the answer
    asserting both a claim and its direct polarity opposite about the
    same subject), not general logical validity. A judge-backed
    evaluator for deeper reasoning-quality checks exists
    (``controlplane.evaluation.judge_evaluators.JudgeBackedEvaluator``
    with ``task="reasoning"``) and is measured in
    docs/EVALUATION/EVALUATOR_RESULTS.md, but is not part of this live
    default suite for the same latency reason."""

    name = "reasoning"

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        if not ctx.answer:
            return EvaluationResult(
                evaluator=self.name, status=EvaluationStatus.IMPLEMENTED, label="NOT_APPLICABLE",
                rationale="no answer to check",
            )
        lowered = ctx.answer.lower()
        contradictions = [f"{pos!r} and {neg!r}" for pos, neg in _CONTRADICTION_PAIRS if pos in lowered and neg in lowered]
        if contradictions:
            return EvaluationResult(
                evaluator=self.name,
                status=EvaluationStatus.IMPLEMENTED,
                label="SELF_CONTRADICTORY",
                issues=contradictions,
                rationale=f"answer asserts both sides of a direct polarity pair: {contradictions}",
                recommended_signal="FLAG_FOR_REVIEW",
            )
        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.IMPLEMENTED,
            label="NO_CONTRADICTION_DETECTED",
            rationale="no direct polarity self-contradiction found (narrow deterministic check only, not general reasoning validity)",
            recommended_signal="OK",
        )


class NotImplementedEvaluator(Evaluator):
    """Placeholder for Bias -- deferred (see docs/PROJECT_STATE/FUTURE_WORK.md
    for the standalone ``controlplane.evaluation.bias`` module, which is
    real but is a paired/comparative evaluator, not a fit for this
    single-context ``Evaluator`` interface). Never fabricates a score;
    reports its own absence explicitly."""

    def __init__(self, name: str) -> None:
        self.name = name

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        return EvaluationResult(
            evaluator=self.name,
            status=EvaluationStatus.NOT_IMPLEMENTED,
            rationale="not implemented this milestone -- see docs/PROJECT_STATE/FUTURE_WORK.md",
        )


class EvaluationSuite:
    """Runs a fixed set of evaluators and returns every result -- never
    silently drops one, even a NOT_IMPLEMENTED one, so the caller can see
    the full, honest picture of what was and wasn't evaluated."""

    def __init__(self, evaluators: list[Evaluator] | None = None) -> None:
        self._evaluators = evaluators or [
            PrivacyPIIEvaluator(),
            ActionRiskEvaluator(),
            SafetyEvaluator(),
            GroundingEvaluator(),
            FactualityEvaluator(),
            ResponseConfidenceEvaluator(),
            ReasoningEvaluator(),
            RAGAdequacyPassthroughEvaluator(),
            NotImplementedEvaluator("bias"),
        ]

    def run(self, ctx: EvaluationContext) -> list[EvaluationResult]:
        return [evaluator.evaluate(ctx) for evaluator in self._evaluators]
