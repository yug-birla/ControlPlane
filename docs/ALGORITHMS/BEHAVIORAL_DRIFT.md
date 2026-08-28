# Behavioral Drift Baseline

**Status:** IMPLEMENTED (standalone, not live-wired) — V0 (Milestone 7, 2026-08-28)

## Problem

Bootstrap SS26: detect when an observed trajectory deviates from normal recent patterns (unexpected tool frequency, unusual data source, unexpected permission, unusual capability transition) as a control signal — not an automatic block.

## Architecture Location

`controlplane/governance/behavioral_drift.py::BehavioralDriftDetector`.

## Method

An interpretable frequency-based baseline (bootstrap SS11): given a history of `(tool, governance_action)` pairs from recent past requests, flags a new proposal as drifted if (a) the proposed tool is rare in that history (below a configurable frequency threshold), and/or (b) the governance outcome is more severe than anything seen in the history. Zero signals → `NONE`; one → `LOW`; both → `MEDIUM`. No `HIGH` level is currently reachable by this V0 (reserved for a future signal, e.g. repeated drift across consecutive requests).

## Why Standalone, Not Live-Wired

This ControlPlane instance does not yet have meaningful real historical `AGENT`-action volume to baseline against — a handful of demo/test requests is not a "normal pattern" to compare against, and flagging drift against an near-empty or arbitrary baseline would be worse than not flagging at all (a false sense of monitoring). Same "standalone until a live path justifies it" reasoning already used for `AgentGate` before Milestone 7 gave it one. Demonstrated instead against a clearly-labeled SYNTHETIC baseline history (`controlplane/experiments/evaluate_behavioral_drift.py`) to prove the mechanism itself works correctly.

## Candidate Alternatives

- **A learned anomaly-detection model** — rejected; no training data exists, and an interpretable frequency baseline is the required starting point (bootstrap SS11).
- **Wiring live into the Decision Engine now** — rejected until real historical volume exists; see above.

## Inputs / Outputs

`detector.assess(history: list[(tool, governance_action)], proposed_tool: str, governance_action: str) -> DriftAssessment` (`level`, `reason`, `signals`, `baseline_sample_count`).

## Dataset

`controlplane/experiments/evaluate_behavioral_drift.py`'s constructed SYNTHETIC history (80% `sql_read_query`/ALLOW, 20% `write_report`/ALLOW — a stated, reasonable "normal" pattern for an internal tools-query workload) + 4 demonstration cases.

## Compute / Latency

Pure Python, no model call, no DB query in the current standalone form — negligible.

## Metrics

4/4 demonstration cases matched their expected drift level (normal continuation → NONE; rare tool → LOW; unprecedented severity → LOW; both → MEDIUM). See `docs/EVALUATION/RESULTS/behavioral_drift_<date>.json`.

## Failure Modes

None observed on the demonstration set (by construction, since the cases were designed to exercise each branch) — not yet tested against real historical volume, which doesn't exist yet.

## Known Limitations

- Not wired into any live request path.
- No real historical baseline exists yet to validate against (SYNTHETIC demonstration only).
- Only two signals (tool rarity, governance severity) — bootstrap SS26 additionally lists unusual data source, permission, destination, workflow length, and capability-transition signals, none implemented yet.
- No `HIGH` drift level is currently reachable.

## Result

A real, working, interpretable mechanism exists and is correctly demonstrated on a synthetic baseline — honestly not yet validated against real usage, because real usage volume doesn't exist yet.

## Final Decision

Adopted as a standalone capability, ready to wire into the live Decision Engine once real historical AGENT-action volume exists to baseline against.

## Version

v1 — 2026-08-28.
