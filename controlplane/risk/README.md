# controlplane/risk/

**Purpose:** the baseline Risk Profiler. See `docs/ALGORITHMS/RISK_PROFILER_BASELINE.md` and `docs/EVALUATION/RISK_PROFILER_RESULTS.md`.

## Interface

- `profile.py`: `RiskProfile`, `RiskSeverity` (reuses the canonical 5-value scale already used throughout `docs/DATA/`), `ControlDepth` (reuses the existing Fast Path/Deep Path vocabulary).
- `baseline.py`: `BaselineRiskProfiler.profile(query, fingerprint) -> RiskProfile` — rules + fingerprint only, no learned model (bootstrap SS9 forbids one at this milestone).

## Dependencies

`controlplane.query_intelligence.fingerprint.QueryFingerprint` (its only real dependency — takes an already-computed fingerprint, doesn't recompute one).

## Limitations

No per-dimension ground truth exists to validate the 9-dimension breakdown against. One documented miss on the single true HIGH_RISK validation example (a decision-support/governance recommendation with no agentic action or keyword trigger) — see the results doc before trusting this for anything safety-critical without `controlplane/policy/`'s independent human-approval gate.

## Extension points

A learned risk model (once a measured gap justifies one, per bootstrap SS21) would implement the same `.profile(query, fingerprint) -> RiskProfile` shape.
