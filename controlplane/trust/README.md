# controlplane/trust/

**Purpose:** the final control-loop output — a structured `HIGH`/`MEDIUM`/`LOW` trust verdict with a stated reason, computed from already-validated signals (never an invented number). See `docs/ALGORITHMS/TRUST_LAYER.md`.

## Interface

- `engine.py`: `TrustLevel` (`HIGH`/`MEDIUM`/`LOW`), `TrustAssessment` (`level`, `reason`, `contributing_factors`), `TrustEngine.assess(verification, decision, risk) -> TrustAssessment`.

## Dependencies

`controlplane.verification.engine`, `controlplane.decision.engine`, `controlplane.risk.profile`.

## Limitations

Only 3 input signals (verification, decision, risk) — bootstrap SS36 also suggests evaluator agreement/data quality/model reliability, none of which have a metric yet to feed this.

## Extension points

Not persisted to its own table by design (pure function of already-persisted data, see `docs/PROJECT_STATE/DECISIONS.md`) — recomputed wherever needed (`controlplane.runtime`, `controlplane.dashboard.queries`).
