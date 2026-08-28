# Evaluation Layer

**Status:** PARTIALLY IMPLEMENTED (Milestone 4/5, 2026-08-28)

## Problem

Score a completed response along multiple independent dimensions (bootstrap: "do not create one LLM for every evaluator") so the Decision Engine has real signals to act on.

## Architecture Location

`controlplane/evaluation/evaluators.py`. `EvaluationSuite` runs a fixed evaluator list; results are per-request-persisted (`response_evaluations` table) and fed to `controlplane/decision/engine.py`.

## Evaluators

| Evaluator | Method | Status |
|---|---|---|
| `privacy_pii` | Deterministic passthrough of Query Profiler `sensitivity` | IMPLEMENTED |
| `action_risk` | Deterministic passthrough of Risk Profiler `action` dimension + severity | IMPLEMENTED |
| `safety` | Deterministic passthrough of Risk Profiler `safety` dimension | IMPLEMENTED |
| `grounding` | Lexical claim/evidence overlap (answer vs. RAG evidence text) | IMPLEMENTED (baseline) |
| `factuality` | Deterministic numeric-claim check against SQL rows + RAG evidence text | IMPLEMENTED (narrow — numeric claims only) |
| `response_confidence` | Hedging-language + length heuristic | IMPLEMENTED (surface signal, not calibrated model confidence) |
| `reasoning` | — | NOT_IMPLEMENTED |
| `bias` | — | NOT_IMPLEMENTED |

None fabricate a score when inapplicable — `NOT_APPLICABLE` (grounding/factuality with no evidence) and `NOT_IMPLEMENTED` (reasoning/bias) are reported explicitly.

## Why Reasoning and Bias Remain Unimplemented

**Reasoning:** bootstrap explicitly forbids inspecting hidden chain-of-thought; a real reasoning evaluator needs a *verifiable* intermediate trace (tool calls, sub-answers) the current single-shot generation doesn't produce. Adding one would require restructuring generation into multiple steps — a larger change than this milestone's scope, and not yet justified by a measured gap.
**Bias:** requires paired demographic test cases (bootstrap §17: "paired demographic examples, consistency comparisons") that don't exist in this project's data yet. Fabricating pairs to fill the gap would risk a bias *measurement* method as unvalidated as the thing it measures.

## Candidate Alternatives

- **LLM-as-a-judge for grounding/factuality** — deferred; the deterministic baselines are measurably useful (Grounding: real end-to-end recovery scenario; Factuality: 0/1 → correctly SUPPORTED once RAG evidence is checked too, see the regression this fix addressed) and add no latency/cost/Gemini-quota consumption.
- **A dedicated small classifier for response_confidence** — deferred; no training data exists, and the heuristic is cheap and already drives a real, tested escalation path.

## Inputs / Outputs

`EvaluationContext(query, answer, evidence_texts, sql_rows, fingerprint, risk) -> list[EvaluationResult]`.

## Dataset

Grounding/Factuality validated via targeted unit tests and the real end-to-end control-loop scenarios (`tests/test_control_loop_scenarios.py`), not a large labeled benchmark (none exists for this specific corpus/task combination).

## Metrics

See `docs/EVALUATION/CONTROL_LOOP_RESULTS.md` for the Decision Engine's use of these signals in practice.

## Failure Modes

Found and fixed during this milestone: `FactualityEvaluator` originally checked SQL rows only, causing a correct RAG-sourced number to be flagged `CONTRADICTED` simply for not being SQL data in a multi-source query — fixed to check both evidence sources (regression test: `test_factuality_checks_rag_evidence_too_not_only_sql_regression`).

## Result

6/8 evaluators real and wired into the live control loop; 2/8 explicitly and honestly not implemented.

## Final Decision

Current evaluator set adopted as the runtime default.

## Version

v2 — 2026-08-28 (v1 was Milestone 4's privacy/action_risk/grounding-only set).
