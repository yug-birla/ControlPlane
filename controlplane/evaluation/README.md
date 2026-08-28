# controlplane/evaluation/

**Purpose:** the Evaluation layer — scores a completed response along multiple independent dimensions. See `docs/ALGORITHMS/EVALUATION_LAYER.md` for method/status per evaluator.

## Interface

- `evaluators.py`: `Evaluator` (ABC), `EvaluationContext`, `EvaluationResult`, `EvaluationSuite`. Real: `PrivacyPIIEvaluator`, `ActionRiskEvaluator`, `SafetyEvaluator`, `GroundingEvaluator`, `FactualityEvaluator`, `ResponseConfidenceEvaluator`, `ReasoningEvaluator` (narrow, deterministic self-contradiction check), `RAGAdequacyPassthroughEvaluator`. Not implemented in this suite: `bias` (via `NotImplementedEvaluator` — real implementation lives in `bias.py`, see below).
- `bias.py`: `BiasEvaluator.assess_pair(case_id, answer_a, answer_b) -> BiasPairAssessment` — a standalone, comparative evaluator (needs two answers, doesn't fit the single-context `Evaluator` ABC).
- `judge_evaluators.py`: `JudgeBackedEvaluator` — adapts `controlplane.judge.{LocalJudge,RemoteJudge}` to the `Evaluator` interface; real and swappable, but not in `EvaluationSuite()`'s default list (latency, see `docs/ALGORITHMS/LLM_JUDGE.md`).

## Dependencies

`controlplane.query_intelligence.fingerprint`, `controlplane.risk.profile` — no model call, no DB access (persistence happens in `controlplane.runtime`). `judge_evaluators.py` additionally depends on `controlplane.judge`.

## Limitations

Grounding/Factuality are lexical/numeric-overlap baselines, not semantic entailment (a judge-backed semantic alternative exists but isn't the live default). Reasoning is a narrow single-pattern check, not general logical validity. Bias is real but standalone/comparative, not part of the per-request suite.

## Extension points

`controlplane.decision.engine.DecisionEngine` consumes `EvaluationResult` by `evaluator` name (`grounding`, `factuality`, `response_confidence`, `action_risk`, `rag_adequacy`) — a new evaluator becomes decision-relevant by adding one more `_find(...)` check there.
