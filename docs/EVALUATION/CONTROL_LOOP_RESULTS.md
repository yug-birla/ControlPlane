# Control Loop Results — Decision, Intervention, Replan, Verification

**Run:** `controlplane/experiments/evaluate_control_loop_before_after.py`, 2026-08-28. See `docs/ALGORITHMS/CONTROL_LOOP.md` for the method. Raw output: `RESULTS/control_loop_before_after_2026-08-28.json`.

## Method — What This Measures and What It Doesn't

Uses **scripted model responses** (the same technique as `tests/test_control_loop_scenarios.py`), not live Groq/Gemini calls at scale. This measures whether the control-loop *mechanism* changes outcomes on deliberately-constructed inputs — a real, controlled experiment — not aggregate live-model quality improvement across many real prompts, which would need a much larger model-comparison budget. **NOT MEASURED:** live-model statistical improvement rate.

For each scenario: **BASELINE** = the first model response, returned unconditionally (what a system without ControlPlane's control loop would do). **CONTROLPLANE** = the actual final answer after the full Decide → Intervene → Replan → re-Evaluate → Verify loop. Both are scored with the *identical* Grounding/Confidence evaluators.

## Headline Numbers (5 scenarios)

| Metric | Value |
|---|---|
| Scenarios where ControlPlane intervened | 3/5 |
| Scenarios improved over baseline (grounding or confidence) | 2/5 |
| Scenarios with a safety-correct abstention (declined rather than asserted a bad answer) | 1/5 |
| Unnecessary interventions (intervened but neither improved nor safely abstained) | **0/5** |
| Avg. extra latency per request (scripted 250ms/call) | 150ms |

## Per-Scenario Detail

| Scenario | Baseline | ControlPlane | Decision | Verification |
|---|---|---|---|---|
| `rag_recovery` | grounding=UNSUPPORTED | grounding=SUPPORTED | CONTINUE (attempt 2) | VERIFIED |
| `rag_exhausted` | grounding=UNSUPPORTED | (declined — ASK_CLARIFICATION) | ASK_CLARIFICATION | NOT_VERIFIED |
| `model_escalation` | confidence=LOW (hedging) | confidence=MEDIUM, role=STRONG | CONTINUE (attempt 2) | VERIFIED |
| `clean_no_intervention_needed` | confidence=MEDIUM | unchanged | CONTINUE (attempt 1) | VERIFIED |
| `clean_rag_already_grounded` | grounding=SUPPORTED | unchanged | VERIFY (attempt 1) | VERIFIED |

## A Bug Found While Reading These Results (Not Hidden)

The first run of this script reported 1/5 improved and 2/5 "unnecessary" interventions. Inspecting the raw per-scenario output found the comparison logic itself was wrong two ways: (1) it only checked the *grounding* rank, so the `model_escalation` scenario's real confidence improvement (LOW→MEDIUM) was invisible to the metric; (2) it had no way to credit `rag_exhausted`'s correct, safety-motivated abstention as anything but "not improved." Fixed to check both grounding *and* confidence, and to track abstention as its own outcome — corrected numbers are the ones above. Kept in this document rather than only in commit history, per the project's "never hide a measurement bug" standard.

## Real End-to-End Trace — RAG Self-Healing (Scenario 5, mandatory)

Query: *"What is the meal reimbursement limit according to the travel policy?"*

1. Attempt 1: model (scripted) answers "The weather forecast predicts rain tomorrow..." — unrelated to the query.
2. `grounding` evaluator: `UNSUPPORTED` (0% term overlap with retrieved evidence).
3. Decision Engine: `RETRIEVE_MORE` (attempt 1, can_retry=True).
4. `RETRIEVAL_INSUFFICIENT` → `INTERVENTION_TRIGGERED` → `REPLAN_TRIGGERED` events fire; RAG re-executed with k=10 (was 5); prompt rebuilt with the (same, since retrieval was already at the ceiling for this tiny corpus) evidence; model re-invoked.
5. Attempt 2: model answers "Meal reimbursement is up to $75/day domestic, $100/day international, per the travel policy."
6. `grounding` evaluator: `SUPPORTED`.
7. Decision Engine: `CONTINUE` (attempt 2). Verification: `VERIFIED`.

Full event sequence: `QUERY_RECEIVED, QUERY_PROFILED, RISK_DETECTED, PLAN_CREATED, MODEL_CALLED, ROUTE_STARTED×3, ROUTE_COMPLETED×3, EVALUATION_COMPLETED, RETRIEVAL_INSUFFICIENT, INTERVENTION_TRIGGERED, REPLAN_TRIGGERED, MODEL_CALLED, REPLAN_COMPLETED, EVALUATION_COMPLETED, FINAL_RESPONSE_GENERATED`. Permanently regression-tested: `tests/test_control_loop_scenarios.py::test_rag_self_healing_recovers_from_an_ungrounded_first_answer`.

## Real End-to-End Trace — Model Escalation (Scenario 8, mandatory)

Query: *"What is the capital of France?"* Attempt 1 (FAST role, scripted): "I'm not sure, it's unclear to me." → `response_confidence=LOW` → Decision: `CHANGE_MODEL` → `MODEL_ESCALATION` event → re-invoked with STRONG role → Attempt 2: "The capital of France is Paris, a well-established fact." → Decision: `CONTINUE`, Verification: `VERIFIED`. Test: `test_low_confidence_fast_response_escalates_to_strong_model`.

## Real End-to-End Trace — High-Risk Control (Scenario 7, mandatory)

Query: the QP-190 governance/decision-support case (permanent HIGH_RISK regression from Milestone 3). Risk severity `HIGH_RISK` → `action_risk` evaluator confirms `HIGH_RISK` → Decision Engine: `HUMAN_REVIEW` (hard constraint, checked first, regardless of grounding/confidence) → Verification: `REJECTED` (not final until a human approves) — but a draft answer is still returned (graceful degradation, not a withheld response). Test: `test_high_risk_action_reaches_human_review_not_continue`.

## Known Limitations

- 5-scenario sample — a controlled demonstration of the mechanism, not a statistically powered benchmark.
- No live-model statistics (NOT MEASURED — no budget for a larger real-model comparison this milestone).
- `max_attempts=2` means every scenario here resolves in at most one retry; higher budgets are untested.
