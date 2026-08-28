# controlplane/evaluation/

**Purpose:** the Evaluation layer — scores a completed response along multiple independent dimensions. See `docs/ALGORITHMS/EVALUATION_LAYER.md` for method/status per evaluator.

## Interface

- `evaluators.py`: `Evaluator` (ABC), `EvaluationContext`, `EvaluationResult`, `EvaluationSuite`. Real: `PrivacyPIIEvaluator`, `ActionRiskEvaluator`, `SafetyEvaluator`, `GroundingEvaluator`, `FactualityEvaluator`, `ResponseConfidenceEvaluator`. Not implemented: `reasoning`, `bias` (via `NotImplementedEvaluator`).

## Dependencies

`controlplane.query_intelligence.fingerprint`, `controlplane.risk.profile` — no model call, no DB access (persistence happens in `controlplane.runtime`).

## Limitations

Grounding/Factuality are lexical/numeric-overlap baselines, not semantic entailment. Reasoning/Bias are honestly `NOT_IMPLEMENTED`, not faked.

## Extension points

`controlplane.decision.engine.DecisionEngine` consumes `EvaluationResult` by `evaluator` name (`grounding`, `factuality`, `response_confidence`, `action_risk`) — a new evaluator becomes decision-relevant by adding one more `_find(...)` check there.
