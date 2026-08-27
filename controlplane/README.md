# controlplane/ (Milestone 3 — Adaptive Execution: Execution Graph, Capability Router, Model Router)

**Purpose:** the runtime backbone plus a real Query Profiler, Risk Profiler, Policy baseline, Capability Router, Model Router, and Execution Graph — still no RAG, evaluation, intervention, or replanning.

## Interface

- `POST /v1/requests {"query": str, "application_id": str | null}` → `ResponseEnvelope` (`request_id`, `trace_id`, `trajectory_id`, `status`, `answer`, `metadata`). `metadata` now also includes `capability_route` (selected capabilities, restricted-removed, the executed `ExecutionGraph`) and `model_route` (action, role, verification/approval flags) — see `controlplane/schemas.py`.
- `GET /health/live`, `GET /health/ready` (checks real Postgres connectivity).
- `controlplane.runtime.Runtime.handle(ctx, state) -> state` — orchestrates: persist request/trajectory → `QUERY_RECEIVED` → Query Profiler → `QUERY_PROFILED` → Risk Profiler + Policy → `RISK_DETECTED` → Capability Router + Model Router → `PLAN_CREATED` (+ `HUMAN_REVIEW_REQUIRED` when applicable) → `GraphExecutor` runs the `ExecutionGraph` (`ROUTE_STARTED`/`ROUTE_COMPLETED` per node; the `"generation"` node invokes the configured model provider for the routed FAST/STRONG role) → model invocation record → ledger entry → `MODEL_CALLED`/`MODEL_FAILURE` → `FINAL_RESPONSE_GENERATED` → update trajectory. `build_default_runtime()` wires real dependencies; tests inject fakes for `provider_factory`, `query_profiler`, `risk_profiler`, `policy`, `capability_router`, `model_router`.
- `controlplane/execution/`, `controlplane/routing/` (new this milestone), `controlplane/query_intelligence/`, `controlplane/risk/`, `controlplane/policy/`, `controlplane/experiments/`, `controlplane/models/` (Groq now resolved per FAST/STRONG role), `controlplane/trajectory/`, `controlplane/ledger/`, `controlplane/events/`, `controlplane/db/` — see each subfolder's own `README.md`.

## Dependencies

Milestone 2's stack, unchanged (no new third-party dependency this milestone — `controlplane/execution/executor.py` uses only `concurrent.futures` from stdlib).

## Limitations (intentional, Milestone 3 scope)

- SQL/RAG/WEB/CHAT_HISTORY/MEMORY/AGENT capabilities have no real implementation — a query can be *routed* to them (the `ExecutionGraph` will contain the node, in the correct dependency position), but the `GraphExecutor` runs them via an explicit `MOCKED` handler, never fabricated data (Layer 5/11/18, see `docs/PROJECT_STATE/FUTURE_WORK.md`).
- Model Router only distinguishes FAST vs. STRONG, both resolved to Groq (`GROQ_MODEL_FAST`/`GROQ_MODEL_STRONG`, falling back to `GROQ_MODEL`) — no local generative model pool yet (see `docs/PROJECT_STATE/DECISIONS.md` for why the Qwen3 tier from `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md` was deferred).
- `ROUTE_STARTED`/`ROUTE_COMPLETED` events are emitted after the whole graph finishes, not live per-node (see `controlplane/execution/README.md`).
- The Risk Profiler's Milestone 2 HIGH_RISK miss (`QP-190`) is fixed this milestone (see `docs/EVALUATION/RISK_PROFILER_RESULTS.md`) but a new, unrelated false positive (`QP-198`, a sensitivity-classification error) was discovered and documented, not silently fixed.
- No RAG, no evaluators, no Intervention Engine, no Replanner, no Behavioral Drift, no Shadow Mode.

## Extension points for later layers

- Layer 5/11/18 (real SQL/RAG/Agent capabilities): implement a handler function and register it in `GraphExecutor(handlers={...})` — no change needed to `controlplane/execution/` or `controlplane/routing/`.
- Layer 10 (multi-provider Model Routing): `controlplane/models/registry.py::get_configured_provider(settings, role=...)` currently always returns a `GroqProvider`; adding a second provider (or a local generative model) means extending this one function, not the router.
- Milestone 4+ (RAG, Evaluation, Intervention, Replanning): the `ExecutionGraph`/`GraphExecutor` and `route_decisions` table are designed to be the substrate these build on, not something they replace.
