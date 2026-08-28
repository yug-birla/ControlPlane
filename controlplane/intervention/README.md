# controlplane/intervention/

**Purpose:** the Intervention Engine — translates a `ControlDecision` into an executable spec. See `docs/ALGORITHMS/CONTROL_LOOP.md`.

## Interface

- `engine.py`: `InterventionType` (enum), `InterventionSpec`, `InterventionEngine.plan(decision, current_model_role) -> InterventionSpec`.

## Dependencies

`controlplane.decision.engine`. Pure planning step — `controlplane.runtime` actually executes the spec (re-retrieval, re-invocation).

## Limitations

`RETRIEVE_MORE` widens `k`, not LLM-based query reformulation (deferred, see `docs/PROJECT_STATE/DECISIONS.md`).

## Extension points

A `RERANK`/`CHANGE_DATA_SOURCE` intervention type would add one `InterventionType` member and one branch in `.plan(...)`.
