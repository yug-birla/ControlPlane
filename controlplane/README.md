# controlplane/ (Layer 1 — Foundation)

**Purpose:** the runtime skeleton a request passes through — API entry, identity, execution state, config, logging, errors, health — with no intelligence, routing, or capability logic yet.

## Interface

- `POST /v1/requests {"query": str, "application_id": str | null}` → `ResponseEnvelope` (`request_id`, `trace_id`, `trajectory_id`, `status`, `answer`, `metadata`). See `controlplane/schemas.py`.
- `GET /health/live`, `GET /health/ready` — see `controlplane/api/health.py`.
- `controlplane.state.ExecutionState` — the typed context every future layer extends via `metadata` until a field earns a permanent place (query profile, risk state, evidence, etc. per `docs/architecture/RUNTIME_FLOW.md` §8).
- `controlplane.runtime.Runtime.handle(state) -> state` — the single seam later layers (Query Intelligence, Routing, RAG, Intervention, ...) attach to. Do not add business logic to `api/routes.py`; extend `Runtime` or its future sub-components instead.
- `controlplane.errors.ControlPlaneError` and subclasses — the common error contract; add new error classes here rather than raising bare exceptions.
- `controlplane.context` — `request_id`/`trace_id`/`trajectory_id` generation and the contextvars that make them appear automatically in every structured log line for the duration of a request (`RequestContext.bind()`).

## Dependencies

FastAPI, Pydantic, Uvicorn only (see `pyproject.toml`). No database, cache, vector store, or model provider is connected — `controlplane/config.py` reads their connection strings from the environment but nothing uses them yet.

## Limitations (intentional, Layer 1 scope)

- `Runtime.handle` is a deterministic echo. No query profiling, risk assessment, routing, retrieval, model calls, evaluation, intervention, or replanning exists.
- `ExecutionState` only persists in memory for the duration of one request — no Trajectory Store, no Execution Ledger, no database. Restarting the process loses everything.
- `/health/ready` checks configuration only; it does not ping Postgres/Redis/Qdrant because nothing connects to them yet.
- No event bus — `logger.info(...)` calls in `runtime.py` are plain structured logs, not events on a bus (Layer 3).

## Extension points for later layers

- Layer 2 (Execution State + Trajectory): persist `ExecutionState` and add a real Trajectory Store / Execution Ledger instead of returning state directly from `Runtime.handle`.
- Layer 3 (Event Model): replace the plain `logger.info` step markers in `runtime.py` with real event emission.
- Layer 7+ (Query Intelligence onward): each becomes a component `Runtime` calls in sequence, behind the same `ExecutionState -> ExecutionState` shape.
