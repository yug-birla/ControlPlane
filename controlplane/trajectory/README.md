# controlplane/trajectory/

**Purpose:** the Trajectory Store  -  "reconstructable execution state/history" (`docs/architecture/TRAJECTORY_AND_LEDGER.md`). Distinct from the Execution Ledger (`controlplane/ledger/`), which is append-only consequential facts.

## Interface

`TrajectoryStore`: `create_request`/`update_request_status`, `create_trajectory`/`update_trajectory_status`, `append_step`/`update_step_status`, `get_history` (chronological), `get_trajectory`. See `controlplane/runtime.py` for how these compose into one request's flow.

## Dependencies

`controlplane/db/` (Postgres). No in-memory caching  -  every read goes to the database, which is what makes "persistence across restart" true rather than assumed.

## Limitations

Single-request trajectories only (`trajectory_type="SINGLE_REQUEST"`); no plan/plan_version linkage yet (Layer 4-5), no multi-agent parent/child trajectories (Layer 19).

## Extension points

Future layers (RAG, evaluation, intervention, replanning) append more `trajectory_steps` rows via `append_step`/`update_step_status`  -  they don't need a new store.
