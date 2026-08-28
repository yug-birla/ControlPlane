# Agent / Tool Governance Gate

**Status:** IMPLEMENTED (standalone) — V0 (Milestone 6, 2026-08-28)

## Problem

Bootstrap SS32: a proposed agent tool call should pass through Risk → Policy → Decision → `ALLOW`/`RESTRICT`/`HUMAN_REVIEW`/`BLOCK` before executing, with unrestricted destructive actions never permitted.

## Architecture Location

`controlplane/governance/agent_gate.py`. **Standalone, not yet wired into a live AGENT capability node** — this repo's `AGENT` capability still executes via the `GraphExecutor`'s explicit `MOCKED` handler (Layer 5/18, see `docs/PROJECT_STATE/FUTURE_WORK.md`), so there is no real agent proposing/executing tool calls in the live runtime yet for this gate to actually gate. Stated plainly per bootstrap SS65 ("never claim autonomous governance if it doesn't actually execute yet") — this is a real, tested, measured decision function, ready to be the actual gate once a real agent/tool execution path exists, not a claim that it already is one.

## Method

A pre-execution proposed-action risk check over a tool call's text + its step-level risk label (reusing the existing Risk Profiler's severity vocabulary — no second independent risk classifier, bootstrap SS3): destructive-operation keyword match → `BLOCK`; `HIGH_RISK`/`CRITICAL` step risk → `HUMAN_REVIEW`; sensitive-data-access keyword match → `RESTRICT`; `MEDIUM_RISK` step risk → `RESTRICT`; otherwise → `ALLOW`.

## Candidate Alternatives

- **A learned classifier over `agent_trajectories.json`** — considered; rejected for this milestone in favor of an interpretable rule-based V0 (bootstrap SS11's "start with an interpretable baseline" principle, applied consistently with the Decision Engine and every other V0 in this codebase), with the dataset used for *evaluation*, not training.
- **Extending the gate to predict `CHANGE_DATA_SOURCE`/`DECREASE_COMPUTE`** (two of the dataset's six label values) — rejected: those are post-hoc recovery/cost decisions keyed to a tool call's *result* (e.g. a 404 error), not the proposed action's *inherent* risk. Conflating them into one gate would blur an authorization decision with a replanning decision that belongs elsewhere in the control loop.

## Inputs / Outputs

`gate.evaluate_step(tool_call: str, step_risk: str | None) -> GovernanceDecision` (`action`, `reason`, `triggering_signal`).

## Dataset

`data/raw/generated/agent_trajectories.json` — 75 trajectories, provenance SYNTHETIC, real `expected_control_action` labels. **Never previously consumed by any code** before this milestone (confirmed via `docs/PROJECT_STATE/FUTURE_WORK.md`'s "Deferred / Out of Scope" list, which never mentioned it) — used for evaluation, not training (no training performed).

Ground truth uses a 6-value vocabulary (`KEEP`, `BLOCK`, `HUMAN_REVIEW`, `ABSTAIN`, `CHANGE_DATA_SOURCE`, `DECREASE_COMPUTE`); the gate uses bootstrap SS32's narrower 4-value one (`ALLOW`, `RESTRICT`, `HUMAN_REVIEW`, `BLOCK`). Mapped for comparison: `KEEP→ALLOW`, `BLOCK→BLOCK`, `HUMAN_REVIEW→HUMAN_REVIEW`, `ABSTAIN→HUMAN_REVIEW` (a cautious deferral, closer to "needs oversight"), `CHANGE_DATA_SOURCE→RESTRICT`, `DECREASE_COMPUTE→RESTRICT` (both "proceed, but not via the same unconstrained path"). This collapsing is a real, stated limitation, not hidden.

## Compute / Latency

Pure Python, no model call — negligible.

## Metrics

See `docs/EVALUATION/AGENT_GOVERNANCE_RESULTS.md`: accuracy 0.720, macro-F1 0.756 across 75 trajectories. `BLOCK` and `HUMAN_REVIEW` are both perfect (precision=recall=1.00) — the safety-critical classes. `RESTRICT` has perfect precision (1.00) but low recall (0.34): every disagreement is the gate defaulting to `ALLOW` for a `CHANGE_DATA_SOURCE`/`DECREASE_COMPUTE` case with no destructive keyword or elevated step risk, exactly the documented scope gap above — not a surprise, not hidden.

## Failure Modes

The gate has no signal for "this tool call already failed, try something else" — its 21 disagreements (of 75) are concentrated entirely in that category, not spread across the safety-critical `BLOCK`/`HUMAN_REVIEW` classes.

## Known Limitations

- Not wired into any live execution path (see Architecture Location).
- Keyword-based destructive/sensitive-access detection, same class of brittleness as any keyword list — not evaluated against adversarial phrasing.
- No permission-lineage or trajectory-level accumulation of risk yet (Layer 19, still not started).

## Result

A real, measured, interpretable governance gate exists and correctly handles the safety-critical BLOCK/HUMAN_REVIEW cases perfectly on this dataset; the recovery-strategy gap is real and documented, not concealed behind one aggregate accuracy number.

## Final Decision

Adopted as a standalone, tested capability. Live wiring into a real AGENT capability execution path is future work (see `docs/PROJECT_STATE/FUTURE_WORK.md`).

## Version

v1 — 2026-08-28.
