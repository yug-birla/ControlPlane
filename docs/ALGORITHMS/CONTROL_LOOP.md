# Control Loop: Decision Engine, Intervention Engine, Replanner, Verification, Trust

**Status:** IMPLEMENTED — V1 (Milestone 6 adds CONFLICTING-evidence handling + the Trust Layer, 2026-08-28; V0 baselines were Milestone 5)

## Problem

Through Milestone 4, ControlPlane observed and evaluated a response but never acted on the evaluation — a bad or uncertain answer was returned exactly as generated. This closes that gap: `docs/architecture/RUNTIME_FLOW.md`'s Decide → Intervene/Replan → Verify stages, actually changing execution.

## Architecture Location

`controlplane/decision/engine.py`, `controlplane/intervention/engine.py`, `controlplane/verification/engine.py`, wired together in `controlplane/runtime.py::_run_control_loop`.

## Decision Engine — Baseline

An interpretable policy matrix (bootstrap §11), not a single risk number: checks (in order) a hard `action_risk` constraint, then `rag_adequacy` (CONFLICTING, new this milestone), then `grounding`, `factuality`, `response_confidence`, `require_verification` — each from the Evaluation layer, never re-derived. Actions: `CONTINUE`, `VERIFY`, `RETRIEVE_MORE`, `CHANGE_MODEL`, `REGENERATE`, `ASK_CLARIFICATION`, `HUMAN_REVIEW`. Bounded by `max_attempts` (default 2): once `attempt_number >= max_attempts`, every branch resolves to a terminal action, never another retry.

**Conflicting evidence (new, bootstrap §29):** `rag_adequacy=CONFLICTING` (the RAG evidence disagrees with *itself*, a distinct failure from `grounding=UNSUPPORTED`, which is about the *answer* vs. evidence) → `RETRIEVE_MORE` while retry budget remains (a wider candidate set might surface a resolving/authoritative document not in the first pass), else `ASK_CLARIFICATION` — the system discloses the conflict rather than silently picking one of the disputed values. Never "always retry" (bootstrap explicitly warns against that as the *only* mechanism); once the budget is spent it defers to the user instead of guessing.

## Intervention Engine — Baseline

Maps each retry action to a concrete `InterventionSpec`: `RETRIEVE_MORE` widens RAG's `k` (5→10, not LLM-based query reformulation — deferred, see Decisions); `CHANGE_MODEL` forces the `STRONG` role; `REGENERATE` re-invokes the same role. `controlplane.runtime` executes the spec (real re-retrieval, real second model call) — the Intervention Engine itself never calls a model or capability.

## Replanner

No separate module — a replan is the *record* of a plan-version transition (`replans` table + a new `route_decisions` row with `plan_version` incremented), created by `Runtime._record_replan` whenever `RETRIEVE_MORE`/`CHANGE_MODEL` actually change what will execute. `REGENERATE` does not replan (same plan, same model, a fresh sample).

## Verification — Baseline

Re-reads the final round of Evaluation results plus the terminal `ControlDecision`. `HUMAN_REVIEW` → `REJECTED`; `ASK_CLARIFICATION` → `NOT_VERIFIED`; any blocking evaluator (`grounding=UNSUPPORTED`, `factuality=CONTRADICTED`, `response_confidence=LOW`) → `NOT_VERIFIED`; a partial concern → `PARTIALLY_VERIFIED`; otherwise `VERIFIED`. Never returns `VERIFIED` without having actually checked these. (A CONFLICTING-evidence request that exhausts its retry budget resolves to `ASK_CLARIFICATION`, already covered by the existing rule — no separate Verification change was needed.)

## Trust Layer (new, bootstrap §36)

`controlplane/trust/engine.py::TrustEngine` — computed immediately after Verification, from Verification's status, the Decision Engine's terminal action/attempt count, and Risk severity (never an invented number). See `docs/ALGORITHMS/TRUST_LAYER.md`.

## Candidate Alternatives

- **Confidence-aware adaptive compute / learned cascade controller** (spec §29-33) — deferred; V0 threshold-based bounded retry is the required "interpretable baseline" (bootstrap §11) a learned policy would need to beat with evidence first.
- **LLM-based query reformulation for RETRIEVE_MORE** — deferred; widening `k` is free (no extra model call), and no evidence yet shows it's insufficient for this corpus size.

## Inputs / Outputs

Decision: `(EvaluationResult list, RiskProfile, ModelRouteDecision, attempt_number) -> ControlDecision`. Intervention: `(ControlDecision, current_model_role) -> InterventionSpec`. Verification: `(EvaluationResult list, ControlDecision) -> VerificationResult`.

## Dataset

No training data — deterministic policy logic. Evaluated via 5 scripted end-to-end scenarios (`tests/test_control_loop_scenarios.py`, +1 this milestone for CONFLICTING evidence) and a before/after counterfactual experiment (`docs/EVALUATION/CONTROL_LOOP_RESULTS.md`).

## Compute / Latency

Pure Python, no model call — negligible. Each retry adds exactly one real model invocation (~model latency) and, for `RETRIEVE_MORE`, one re-retrieval (~20-30ms locally).

## Metrics

See `docs/EVALUATION/CONTROL_LOOP_RESULTS.md`: 3/5 scripted scenarios triggered intervention, 2/5 genuinely improved (grounding or confidence), 1/5 correctly and safely abstained rather than asserting a bad answer, 0/5 unnecessary interventions.

## Failure Modes

If the intervention's re-execution itself fails (e.g. model provider error), the loop catches it, records `actual_effect={"status": "FAILED", ...}`, and keeps the pre-intervention result rather than crashing the request (graceful degradation, bootstrap §33).

## Known Limitations

- `max_attempts=2` (one bounded retry) — not tuned, a deliberately conservative default given no evidence yet on the cost/benefit of more retries.
- Verification and Decision use the same evaluator set; there's no independent "verifier model" distinct from the evaluators that fed the decision (spec's suggested separate VERIFIER role is not yet implemented).
- `RISK_ESCALATION` event is declared but not emitted by any code path yet (risk is assessed once, up front, not re-assessed mid-execution).

## Result

The RAG self-healing, model-escalation, and high-risk scenarios all pass as real, permanent end-to-end tests (`tests/test_control_loop_scenarios.py`) — the control loop measurably changes execution, not just observes it.

## Final Decision

V0 baselines adopted as the runtime default (`controlplane/runtime.py`).

## Version

v1 — 2026-08-28.
