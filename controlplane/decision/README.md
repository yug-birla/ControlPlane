# controlplane/decision/

**Purpose:** the Decision Engine — the control-loop stage that decides whether to continue, intervene, or stop, given the Evaluation layer's results. See `docs/ALGORITHMS/CONTROL_LOOP.md`.

## Interface

- `engine.py`: `ControlAction` (enum), `ControlDecision`, `DecisionEngine.decide(evaluation_results, risk, model_decision, attempt_number) -> ControlDecision`.

## Dependencies

`controlplane.evaluation.evaluators`, `controlplane.risk.profile`, `controlplane.routing.model_router`. Pure function — no DB, no model call (persistence happens in `controlplane.runtime`).

## Limitations

V0 interpretable policy matrix, not a learned policy. `max_attempts=2` is a conservative, untuned default.

## Extension points

A learned decision policy would implement the same `.decide(...)` signature.
