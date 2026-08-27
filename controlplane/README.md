# controlplane/ (Milestone 1 — Runtime Backbone + Trajectory + Ledger + Events + Real Model Provider)

**Purpose:** the runtime backbone a request passes through — API entry, identity, persistent trajectory/ledger, the canonical event contract, and a real model provider (Groq) — with no query intelligence, routing, RAG, evaluation, or intervention yet.

## Interface

- `POST /v1/requests {"query": str, "application_id": str | null}` → `ResponseEnvelope` (`request_id`, `trace_id`, `trajectory_id`, `status`, `answer`, `metadata`). See `controlplane/schemas.py`.
- `GET /health/live`, `GET /health/ready` (now checks real Postgres connectivity) — see `controlplane/api/health.py`.
- `controlplane.state.ExecutionState` — the typed in-request context; `metadata` is still the extension point until a field earns a permanent place.
- `controlplane.runtime.Runtime.handle(ctx, state) -> state` — the single seam later layers (Query Intelligence, Routing, RAG, Intervention, ...) attach to. Orchestrates: persist request/trajectory → emit `QUERY_RECEIVED` → invoke the configured model provider → persist the model invocation → append a ledger entry → emit `MODEL_CALLED`/`MODEL_FAILURE` → emit `FINAL_RESPONSE_GENERATED` → update trajectory. `build_default_runtime()` wires the real dependencies; tests inject fakes via `provider_factory`.
- `controlplane.errors.ControlPlaneError` and subclasses — unchanged from Layer 1, now also covers provider/storage failures (`DependencyError`, `TimeoutError`).
- `controlplane/trajectory/`, `controlplane/ledger/`, `controlplane/events/`, `controlplane/models/`, `controlplane/db/` — see each subfolder's own `README.md`.

## Dependencies

FastAPI, Pydantic, Uvicorn, SQLAlchemy, psycopg2, Alembic, the `groq` SDK. PostgreSQL is a real, required dependency now — see `docker-compose.yml` (an isolated `controlplane_postgres` container on host port 5433, separate from any other project's Postgres on this machine). `GROQ_API_KEY`/`GROQ_MODEL` are read from the environment only; unset means the API returns a structured `CONFIGURATION_ERROR` rather than crashing or faking a response.

## Limitations (intentional, Milestone 1 scope)

- One query always goes to the one configured model, unmodified — no prompt engineering, no query profiling, no routing, no retries, no RAG, no evaluation, no intervention, no replanning.
- Event transport is in-process and synchronous — no cross-process delivery guarantee (see `controlplane/events/README.md`).
- No plan/plan_version concept yet — `ExecutionState.plan_id`/`plan_version` stay `None`; no `PLAN_CREATED` event is emitted (nothing naturally creates a plan yet).
- `/health/ready` checks Postgres only; Redis/Qdrant remain unused placeholders.

## Extension points for later layers

- Layer 4 (Execution Graph): the trajectory already models steps chronologically; add plan/node concepts on top rather than replacing `trajectory_steps`.
- Layer 5 (MCP/Capability Fabric): more `ModelProvider`-shaped abstractions (a `Capability` interface) plug in beside `controlplane/models/`.
- Layer 7+ (Query Intelligence onward): each becomes a component `Runtime` calls before/after the model invocation, behind the same `ExecutionState`-in/out shape.
- Layer 10 (Model Routing): `controlplane/models/registry.py` grows from "return the one configured provider" into an actual router choosing between multiple registered providers.
