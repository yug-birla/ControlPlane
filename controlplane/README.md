# controlplane/ (Milestone 2 — Query Intelligence + Risk Baseline + Local HF Models + Experiment Tracking)

**Purpose:** the runtime backbone plus a real Query Profiler, Risk Profiler, and Policy baseline — no capability/model routing, RAG, evaluation, intervention, or replanning yet.

## Interface

- `POST /v1/requests {"query": str, "application_id": str | null}` → `ResponseEnvelope` (`request_id`, `trace_id`, `trajectory_id`, `status`, `answer`, `metadata`). `metadata` now includes real (not fabricated) `query_profile`, `risk`, and `policy` objects — see `controlplane/schemas.py`.
- `GET /health/live`, `GET /health/ready` (checks real Postgres connectivity).
- `controlplane.runtime.Runtime.handle(ctx, state) -> state` — orchestrates: persist request/trajectory → `QUERY_RECEIVED` → Query Profiler → persist `query_profiles` row → `QUERY_PROFILED` → Risk Profiler + Policy → `RISK_DETECTED` → invoke the configured model provider → persist model invocation → ledger entry → `MODEL_CALLED`/`MODEL_FAILURE` → `FINAL_RESPONSE_GENERATED` → update trajectory. `build_default_runtime()` wires real dependencies; tests inject fakes for `provider_factory`, `query_profiler`, `risk_profiler`, `policy`.
- `controlplane/query_intelligence/`, `controlplane/risk/`, `controlplane/policy/`, `controlplane/experiments/`, `controlplane/models/` (now includes a local embedding provider alongside Groq), `controlplane/trajectory/`, `controlplane/ledger/`, `controlplane/events/`, `controlplane/db/` — see each subfolder's own `README.md`.

## Dependencies

Milestone 1's stack plus `huggingface_hub`, `sentence-transformers` (and its `torch` dependency, CPU-only — see root `README.md` for the install command that avoids pulling a CUDA build). The local embedding model must be downloaded once via `controlplane.models.model_download` before the profiler (and its tests) will work — see root `README.md`.

## Limitations (intentional, Milestone 2 scope)

- Route/capability hints are informational only — every query still goes to the one configured Groq model regardless of what the profiler says (no capability/model routing yet, per bootstrap SS2/SS28).
- Complexity classification is close to chance-level for both Query Profiler baselines — see `docs/EVALUATION/QUERY_PROFILER_RESULTS.md` before relying on it.
- The Risk Profiler missed the one true HIGH_RISK example in its validation set (a governance/decision-support recommendation with no agentic action) — see `docs/EVALUATION/RISK_PROFILER_RESULTS.md`. Mitigated in practice by `PolicyBaseline`'s independent human-approval gate at HIGH_RISK/CRITICAL, not by profiler accuracy alone.
- No RAG, no capability/model router, no evaluators, no Intervention Engine, no Replanner, no Behavioral Drift, no Shadow Mode.

## Extension points for later layers

- Layer 9 (Data/Capability Routing): `capability_hints`/`data_requirement` on `QueryFingerprint` are already the intended input.
- Layer 10 (Model Routing): `controlplane/models/registry.py` grows from "return the one configured provider" into an actual router; `model_registry` already has rows for both the local and remote models to route between.
- Layer 11+ (RAG): the local embedding model (`controlplane/models/local_hf_provider.py`) was deliberately selected to double as the retrieval encoder — no second embedding model download needed.
