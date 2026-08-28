# Agent Governance Gate Results

**Run:** `controlplane/experiments/evaluate_agent_governance.py`, 2026-08-28. See `docs/ALGORITHMS/AGENT_GOVERNANCE.md` for method and the ground-truth label-mapping rationale.

## Dataset

`data/raw/generated/agent_trajectories.json` — 75 trajectories, provenance SYNTHETIC, real `expected_control_action` labels. Never previously consumed by any code before this milestone.

## Results

| Metric | Value |
|---|---|
| Accuracy | 0.720 |
| Macro-F1 | 0.756 |
| Errors | 21/75 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ALLOW | 0.34 | **1.00** | 0.51 | 11 |
| RESTRICT | **1.00** | 0.34 | 0.51 | 32 |
| HUMAN_REVIEW | **1.00** | **1.00** | **1.00** | 21 |
| BLOCK | **1.00** | **1.00** | **1.00** | 11 |

## Interpretation

The safety-critical classes are perfect: every trajectory that should have been `BLOCK`ed was blocked, and every trajectory that should have gone to `HUMAN_REVIEW` did (recall=1.00 for both — bootstrap SS19's "prioritize false-negative analysis for high-risk categories" is satisfied here with zero misses). All 21 errors are the gate defaulting to `ALLOW` where the ground truth (collapsed from `CHANGE_DATA_SOURCE`/`DECREASE_COMPUTE`) expected `RESTRICT` — exactly the documented scope gap: those are post-hoc recovery/cost decisions keyed to a tool call's *result* (e.g. a failed lookup), not the proposed action's *inherent* risk, and this gate is a pre-execution authorization check with no signal for "this already failed." `RESTRICT`'s precision is still 1.00 — when the gate *does* say RESTRICT, it is never wrong, it just doesn't fire often enough to catch the recovery-strategy cases.

## Known Limitations

- 6-value ground truth collapsed to a 4-value vocabulary (see algorithm doc) — a real methodological simplification, not hidden.
- Gate evaluated only at the trajectory's labeled intervention point (or last step if none) — not evaluated per-step across the whole trajectory.
- Not wired into any live execution path (`AGENT` capability is still `MOCKED`).
