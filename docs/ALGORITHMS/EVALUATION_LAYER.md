# Evaluation Layer

**Status:** PARTIALLY IMPLEMENTED (Milestone 7 adds Agent-Governance passthrough + Prompt-Injection detection, 2026-08-28; Reasoning/RAG-adequacy/Bias were Milestone 6; core set was Milestone 4/5)

## Problem

Score a completed response along multiple independent dimensions (bootstrap: "do not create one LLM for every evaluator") so the Decision Engine has real signals to act on.

## Architecture Location

`controlplane/evaluation/evaluators.py`. `EvaluationSuite` runs a fixed evaluator list; results are per-request-persisted (`response_evaluations` table) and fed to `controlplane/decision/engine.py`. `controlplane/evaluation/bias.py` and `controlplane/evaluation/judge_evaluators.py` are separate modules (see below for why).

## Evaluators

| Evaluator | Method | Status |
|---|---|---|
| `privacy_pii` | Deterministic passthrough of Query Profiler `sensitivity` | IMPLEMENTED |
| `action_risk` | Deterministic passthrough of Risk Profiler `action` dimension + severity | IMPLEMENTED |
| `safety` | Deterministic passthrough of Risk Profiler `safety` dimension | IMPLEMENTED |
| `grounding` | Lexical claim/evidence overlap (answer vs. RAG evidence text) | IMPLEMENTED (baseline); semantic (judge-backed) alternative measured separately, see `docs/ALGORITHMS/LLM_JUDGE.md` |
| `factuality` | Deterministic numeric-claim check against SQL rows + RAG evidence text | IMPLEMENTED (narrow — numeric claims only) |
| `response_confidence` | Hedging-language + length heuristic | IMPLEMENTED (surface signal, not calibrated model confidence) |
| `reasoning` | Deterministic self-contradiction check (direct polarity-pair assertions about the same subject) | IMPLEMENTED (narrow — one failure pattern, not general logical validity; measured recall even within scope is only 0.5, see `docs/EVALUATION/EVALUATOR_RESULTS.md`; judge-backed alternative exists but is not live-wired) |
| `rag_adequacy` | Deterministic passthrough of the RAG capability's own adequacy label (incl. `CONFLICTING`) | IMPLEMENTED |
| `agent_governance` (NEW, Milestone 7) | Deterministic passthrough of the AGENT capability's own governance decision | IMPLEMENTED |
| `prompt_injection` (NEW, Milestone 7) | Deterministic fixed-phrase-list check for known injection phrasing in the query | IMPLEMENTED (narrow — verbatim known phrasings only, not paraphrases; measured 1.0 accuracy including near-miss negatives, see `docs/EVALUATION/EVALUATOR_RESULTS.md`) |
| `bias` (in `EvaluationSuite`) | — | NOT_IMPLEMENTED (real, but comparative — see `controlplane.evaluation.bias` below) |

None fabricate a score when inapplicable — `NOT_APPLICABLE`, `NOT_IMPLEMENTED`, `PARSE_FAILED` are reported explicitly rather than guessed.

## Bias — A Standalone Comparative Module

`controlplane/evaluation/bias.py::BiasEvaluator` is real and implemented, but is NOT one of the 9 evaluators in `EvaluationSuite()`'s per-request list: bias is inherently a PAIRED comparison (does the system treat two otherwise-identical inputs differently), and every other evaluator here scores exactly one `EvaluationContext`. Forcing bias into that single-context interface would mean either scoring each side alone (defeating the purpose) or threading a second context through every other evaluator's signature for one evaluator's sake. It is used by `controlplane/experiments/evaluate_bias.py` against a hand-authored 8-pair counterfactual dataset — see `docs/EVALUATION/EVALUATOR_RESULTS.md`.

## Why Reasoning Was Upgraded, Not Left `NOT_IMPLEMENTED`

The self-contradiction check needed no multi-step trace and no model call — a real, if narrow, signal was available without either of the blockers that kept it `NOT_IMPLEMENTED` through Milestone 5. It deliberately reports `NO_CONTRADICTION_DETECTED`, not `CONSISTENT`/`SOUND`, so it never overstates what a narrow keyword-pair check actually verified. A deeper, judge-backed reasoning evaluator also exists (`controlplane.evaluation.judge_evaluators.JudgeBackedEvaluator` with `task="reasoning"`) and is measured, but is not part of the live default suite (see `docs/ALGORITHMS/LLM_JUDGE.md` for the latency reason).

## Candidate Alternatives

- **LLM-as-a-judge for grounding/factuality/reasoning as the live default** — built and measured (`controlplane/judge/`), but not wired into `EvaluationSuite()`'s default list: measured Local Judge latency is 30-90s/call on this CPU-only machine, vs. the rest of the suite's sub-100ms total. Remote Judge (Gemini) is fast but explicitly never the default route (quota, bootstrap SS14).
- **A dedicated small classifier for response_confidence** — deferred; no training data exists, and the heuristic is cheap and already drives a real, tested escalation path.

## Inputs / Outputs

`EvaluationContext(query, answer, evidence_texts, sql_rows, rag_adequacy, fingerprint, risk) -> list[EvaluationResult]`.

## Dataset

Grounding/Factuality/Reasoning validated via targeted unit tests and the real end-to-end control-loop scenarios (`tests/test_control_loop_scenarios.py`). Judge calibration: a DERIVED 20-case grounding benchmark from `rag_cases.json` (see `docs/EVALUATION/EVALUATOR_RESULTS.md`). Bias: `data/raw/generated/bias_paired_cases.json` (NEW, 8 pairs, provenance HUMAN, SMOKE_TEST scale).

## Metrics

See `docs/EVALUATION/CONTROL_LOOP_RESULTS.md` for the Decision Engine's use of these signals in practice, and `docs/EVALUATION/EVALUATOR_RESULTS.md` for the judge calibration and bias results.

## Failure Modes

Found and fixed in Milestone 5: `FactualityEvaluator` originally checked SQL rows only, causing a correct RAG-sourced number to be flagged `CONTRADICTED` simply for not being SQL data in a multi-source query. Found and fixed this milestone: the Local Judge's JSON prompt template had a doubled-brace formatting bug causing every judge call to fail parsing (see `docs/ALGORITHMS/LLM_JUDGE.md`).

## Result

10/11 `EvaluationSuite` evaluators real and wired into the live control loop (only `bias` remains `NOT_IMPLEMENTED` there, by design — it lives as a standalone comparative module instead, also real). A working LLM-Judge subsystem exists and is measured, deliberately not defaulted into the live path -- and this milestone's HARD judge benchmark (`docs/EVALUATION/EVALUATOR_RESULTS.md`) finally gives it a benchmark where it shows a real, if partial, advantage over the deterministic baseline (paraphrase recognition, some subtle-number errors), not just parity or a loss.

## Final Decision

Current evaluator set adopted as the runtime default; judge-backed evaluators adopted for offline calibration/comparison use only.

## Version

v4 — 2026-08-28 (v3 was Milestone 6's Reasoning-upgrade/RAG-adequacy-passthrough set; v2 was Milestone 5's 6-implemented/2-not set; v1 was Milestone 4's privacy/action_risk/grounding-only set).
