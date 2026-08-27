# ControlPlane.ai — Progress Log

Reverse-chronological. Each entry: what happened, evidence.

## 2026-08-28 — Milestone 2: Query Intelligence + Risk Baseline + Local HF Models + Experiment Tracking

Authorized explicitly after Milestone 1. Inspected hardware first (CPU: i7-13620H 10c/16t; RAM: 15.7GB; GPU: none discrete; disk: ~117GB free) before selecting any model, per instruction. Selected `sentence-transformers/all-MiniLM-L6-v2` (verified live against the HF API: apache-2.0, ~22.7M params corroborated by file-size math, 384-dim, 256-token max) as the sole local model — one embedding model, no redundant second model for the same role.

Installed `huggingface_hub`+`sentence-transformers` and started the model download in the background immediately, continuing implementation (DB schema for `query_profiles`/`model_registry`/experiment-tracking tables) while it fetched (~443s for the full repo snapshot, including unused ONNX/OpenVINO/TF variants pulled by `snapshot_download`'s default "fetch everything" behavior — a known minor inefficiency, not corrected since disk isn't constrained). Verified fully offline load afterward.

Built, together: `controlplane/query_intelligence/` (rules baseline + embedding k-NN baseline + hybrid combiner), `controlplane/risk/` (9-dimension rules+fingerprint baseline, reusing the already-canonical `RiskSeverity` scale rather than inventing a fourth one), `controlplane/policy/` (baseline tier mapping), `controlplane/experiments/` (Postgres-backed experiment tracking + dependency-free metrics + 4 runnable evaluation scripts), and wired all of it into `controlplane/runtime.py` between `QUERY_RECEIVED` and the (unchanged) model invocation step.

**Real bugs found and fixed, not just features shipped:**
1. `EmbeddingKNNQueryProfiler.profile()` constructed a fresh `LocalHFEmbeddingProvider()` (reloading model weights from disk) on every single call — ~2s wasted per query. Fixed with a module-level `@lru_cache` provider getter; warm latency dropped from ~21s to ~30ms per call.
2. The Hybrid profiler's rule-vs-knn arbitration checked `field in rule_fp.explanation` to decide whether to trust the rule — but the rules baseline unconditionally sets an explanation for `complexity`/`ambiguity` even on its own generic word-count/question-mark fallback, so those two fields could never actually defer to k-NN regardless of confidence. Fixed by adding an explicit `high_confidence_fields` list, populated only on real keyword/pattern matches; the fallback heuristics no longer masquerade as confident decisions.
3. Found while fixing #2: a copy-paste bug had `impact` checking the `"intent"` key instead of `"impact"` in the same arbitration logic.
4. The initial local-model-unavailable path raised an untyped `EmbeddingProviderError` straight out of the runtime with no mapping to the existing typed error contract — added a `ConfigurationError` mapping (analogous to the missing-Groq-key case) so it fails the same clean way.

**Real evaluation run (not fabricated), against `query_profiles_validation` (28 examples, provenance SYNTHETIC):** Query Profiler complexity accuracy 35.7% for both baselines (near the 33% chance floor -- flagged prominently as a genuine baseline weakness, not hidden); sensitivity 85.7% (rules) vs 78.6% (hybrid) -- rules wins here, called out explicitly since privacy/PII is safety-relevant; capability-hint macro-F1 0.294 (rules) vs 0.355 (hybrid) -- hybrid adopted as the runtime default on this and actionability's win, an empirical choice. Risk Profiler: overall severity accuracy 60.7%; the single true HIGH_RISK validation example was missed (a governance/decision-support recommendation with no agentic action and no keyword match) -- diagnosed and documented as a real failure mode, not glossed over. Local embedding benchmark: cold start 20.1s, warm p50=16ms/p95=32ms/p99=47ms, ~50 QPS single-threaded.

**Local-vs-remote comparison:** harness built and run; local side measured for real; remote (Groq) side explicitly recorded as `NOT_MEASURED` because `GROQ_API_KEY` was not present in this session's environment (checked directly rather than reusing the literal key value from Milestone 1's chat history, to avoid unnecessary secret exposure) -- reported honestly rather than skipped silently or faked.

**Manual end-to-end verification**, all 8 required query types, via a fake model provider (no live Groq key this session -- Milestone 1 already proved that path). Outputs actually inspected: the refund/high-impact-action query correctly reached `HIGH_RISK`, `human_approval_required=True`, and restricted the `AGENT` capability; the PII query reached only `MEDIUM_RISK` and did not escalate `recommended_control_depth` to `DEEP_PATH` (severity-gated design, noted as worth revisiting); a 3-word ambiguous query ("what about it") pulled in noisy, disagreeing k-NN neighbors across 4 different data sources -- an honest, expected limitation of a 135-example exemplar bank for genuinely ambiguous input.

Tests grew from 45 to 80 (query profiler rules/knn/hybrid, risk profiler, policy, local HF provider including "fails cleanly when uncached" and "loads fully offline" cases, model registry seeding). Two Milestone-1-era tests updated to reflect that `risk`/`confidence` in the response are now real, not forbidden-as-fake; the trajectory-step and event-sequence assertions in the integration tests extended for the two new steps/events.

Documentation: `docs/EVALUATION/` created (README, DATASETS, QUERY_PROFILER_RESULTS, RISK_PROFILER_RESULTS, MODEL_BENCHMARKS, RESULTS/ raw JSON); `docs/ALGORITHMS/{LOCAL_EMBEDDING_MODEL,QUERY_PROFILER_BASELINE,RISK_PROFILER_BASELINE}.md` added; 4 new folder READMEs (`query_intelligence/`, `risk/`, `policy/`, `experiments/`); `controlplane/models/README.md` and the top-level `controlplane/README.md` updated; root `README.md`'s run instructions extended with the CPU-only torch install flag and model-download/registry-seed steps.

## 2026-08-27 — Milestone 1: Runtime Backbone + Trajectory + Ledger + Events + Real Model Provider

Authorized explicitly, moving from strict layer-by-layer development to milestone-based development per new instruction ("do NOT create artificial barriers between every architectural layer... implement tightly coupled architecture components together"). Built, together: Trajectory Store, Execution Ledger, Event Model + in-process transport, Model Provider abstraction, Groq provider, and full runtime integration, backed by a real PostgreSQL instance.

**Infrastructure:** Docker Desktop was not running; started it and discovered pre-existing containers from an unrelated project (`lead-intelligence`) already using port 5432 -- left those untouched and stood up an isolated `controlplane_postgres` container on port 5433 via `docker-compose.yml`. Alembic initialized and configured to read `DATABASE_URL` from `controlplane.config` (never from `alembic.ini`, so migrations and the app can never target different databases); initial migration creates `requests`, `trajectories`, `trajectory_steps`, `execution_ledger`, `event_index`, `model_invocations`.

**Code:** `controlplane/db/` (SQLAlchemy models + engine), `controlplane/trajectory/store.py`, `controlplane/ledger/ledger.py`, `controlplane/events/{schema,transport,store}.py`, `controlplane/models/{provider,groq_provider,registry}.py`, `controlplane/runtime.py` rewritten to orchestrate: create request/trajectory -> `QUERY_RECEIVED` -> invoke the configured model provider -> persist the model invocation -> append a ledger entry -> `MODEL_CALLED`/`MODEL_FAILURE` -> `FINAL_RESPONSE_GENERATED` -> update trajectory. Fixed a real bug found via a failing integration test: the `model_invocation` trajectory step never transitioned out of `RUNNING` on the success path (added `TrajectoryStore.update_step_status`). Fixed a second real bug: error responses claimed to carry `request_id`/`trace_id` but those contextvars were always reset (by `RequestContext.bind()`'s cleanup) before the global exception handler read them, so they were always `null` -- fixed by attaching the ids to the exception instance at the point of catching it, while the context is still live.

**Tests:** grew from 19 to 45 (trajectory store, ledger, events, model provider abstraction, Groq provider normalization/error-mapping with a fully mocked SDK client, integration tests exercising the full API-to-Postgres flow with a fake model provider). No automated test calls the live Groq API.

**Live Groq validation:** executed. `tests/manual_groq_live_check.py` asked Groq for its live model list (never hard-coded a model name), selected `allam-2-7b`, and completed a real chat completion (latency 405ms, 18 input / 33 output tokens). Then re-ran the full HTTP pipeline (`POST /v1/requests`) against the same live model and confirmed correct persistence in `trajectories`, `trajectory_steps`, `execution_ledger`, `event_index`, and `model_invocations`. Confirmed by grep across logs and repository files that the API key (pasted into chat by the user) was never written to any file or log. Confirmed restart-persistence by killing the running `uvicorn` process, starting a fresh one, and reading the pre-restart trajectory from a completely independent Python process.

**Documentation:** `docs/architecture/TRAJECTORY_AND_LEDGER.md` and `EVENT_MODEL.md` got "Implementation status" notes distinguishing what's built from what remains a contract; `docs/DATA/POSTGRES_SCHEMA.md` documents the new `model_invocations` table and the TEXT-vs-UUID decision; `docs/ALGORITHMS/MODEL_PROVIDER_ABSTRACTION.md` and `MODEL_INVOCATION_BASELINE.md` created; `controlplane/README.md` and five new subfolder READMEs written; root `README.md` now explains how to run the application.

## 2026-08-27 — Layer 1: Foundation

Authorized explicitly per the implementation bootstrap after the Layer 0 audit. Confirmed no Layer 0 blocker (`BLOCKERS.md` B1–B8) applies to Layer 1 before starting.

Implemented the runtime skeleton: `USER REQUEST → API ENTRY → REQUEST CONTEXT → EXECUTION STATE → TRACEABLE RUNTIME → STRUCTURED RESPONSE`, per §5 of the bootstrap. Stack: Python 3.11, FastAPI, Pydantic v2 (the only concrete stack recommendation in the docs — `SCALE_ARCHITECTURE_UPDATED.md`'s "Prototype stack"). `Runtime.handle()` is a deterministic echo with no intelligence, matching Rule 1 ("no premature intelligence"). Structured logging uses stdlib `logging` + `contextvars` (no new dependency) so `request_id`/`trace_id`/`trajectory_id` appear automatically in every log line for a request's duration without threading them through every function call.

19 tests written and passing (`pytest`). Manually verified end-to-end: started the app with `uvicorn`, exercised `/health/live`, `/health/ready`, `POST /v1/requests` (happy path and validation-error path) with `curl`, and inspected the structured JSON logs to confirm ID consistency across a request's lifecycle. Confirmed by grep that no Layer 2+ concept (Query Profiler, Risk Profiler, Model Router, Capability Router, Evaluator, Intervention Engine, Replanner, Behavioral Drift, MCP routing) was accidentally implemented.

Files: see `docs/PROJECT_STATE/CURRENT_STATE.md` for the full list, and `controlplane/README.md` for the module's interface/limitations/extension points. Design decisions recorded in `DECISIONS.md`.

## 2026-08-27 — Layer 0 Repository Audit

Per the implementation bootstrap's mandatory first task: full repository inspection (structure, code, dependencies, environment, docs). Findings written to `CURRENT_STATE.md`, `BLOCKERS.md`, `FUTURE_WORK.md`, `DECISIONS.md`. Reviewed the original competition brief screenshots in `Problem_Statement/` (Accenture Innovation Challenge 2026, Round 2, Problem Track 1 — "ControlPlane.ai" / "Responsible AI Checker"). Confirmed: zero application code exists; no `AGENTS.md` or `docs/ARCHITECTURE.md` at the paths several docs reference; no `docs/ALGORITHMS/` directory yet.

## 2026-08-27 — Documentation Consistency Audit

Full audit of all 30 `.md` files (~37,600 lines) plus ground-truth JSON schemas, SQL, and generated data files, requested as a standalone task. Git initialized (previously not a repo) with a checkpoint commit (`a0d12d2`), then the audit fixes committed as `4ae6a76`. Key corrections:
- `docs/DATA/SCHEMA.md` rewritten (was corrupted with literal backslash-escapes on every line) and completed with `taxonomy_labels`/`provenance` fields present in the frozen JSON Schema but missing from the doc.
- Dataset record counts corrected against the actual files: `query_profiles_large.json` and `annotation_cases.json` are 270 records, not the 250 every doc claimed.
- `annotation_cases.json` status corrected: fully labeled with synthetic placeholders, not "structure only."
- `POSTGRES_SCHEMA.md`'s enterprise-domain section rewritten to match what `init_postgres_schema.sql` actually creates (NexaConsult Global schema), and the mismatch with the separate CSV-based demo dataset flagged rather than silently merged.
- `POSTGRES_SCHEMA.md`'s Evaluation Database section completed with tables (`responses`, `judgments`, `intervention_labels`, `trajectory_labels`, `experiment_runs`) that `DATA_STORAGE_ARCHITECTURE.md` referenced but that were never defined.
- Intervention taxonomy (16-value `ANNOTATION_GUIDELINES.md` vocabulary) unified across `CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md`, `POSTGRES_SCHEMA.md`, `PRODUCT_THESIS_UPDATED.md`, `README.md`.
- ~157 leftover AI-citation artifacts (`fileciteturn...` tokens) stripped from architecture/specs/data docs.
- Added `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §64 "Terminology Alignment" resolving the highest-impact of the many duplicate vocabularies found (intervention types, top-level decision outcomes, severity scale, model identifiers) — explicitly scoped as partial, not exhaustive (§64.6).
- Fixed `PRODUCT_THESIS_UPDATED.md` internal bugs: duplicate section numbering, mislabeled subsections, an 8-stage vs. 10-stage lifecycle mismatch, a stray blank-section artifact.

Full detail: `docs/DATA/DATA_CHANGELOG.md` v0.4, git commit `4ae6a76`.

## Pre-2026-08-27 — Documentation & Data Sprint (Round 2)

Reconstructed from `docs/DATA/DATA_CHANGELOG.md` v0.1–v0.3 and file evidence; predates this session.
- v0.1 (2026-08-26): Schema v0.1 frozen; 30 representative query profiles created; `docs/DATA/` core docs created (`SCHEMA.md`, `ANNOTATION_GUIDELINES.md`, `DATA_GENERATION.md`, `DATA_STRATEGY.md`, `DATASET_REGISTRY.md`, `EVALUATION_PROTOCOL.md`, `DATA_QUALITY.md`, `DATASET_GAPS.md`). Large-scale generation authorized and executed: 250+ query profiles (later found to actually be 270), 150 RAG cases, 150 intervention cases, 75 counterfactual cases, 75 agent trajectories, 250+ annotation-case structure (later found to be 270), synthetic enterprise environment, evaluation splits.
- v0.2 (2026-08-27): Repository cleanup — deleted a corrupt `smriti-data/` directory (had duplicate/invalid records) after migrating its unique content (NexaConsult + ControlPlane evaluation query sets, `CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md`, `SOURCES_AND_CAPABILITIES.md`, both enterprise SQL files) into the current structure.
- v0.3 (2026-08-27): Root-level `.md` files reorganized into `docs/architecture/`, `docs/specs/`, `docs/DATA/`; `README.md` created as the repository navigation guide.

Team split referenced throughout the data docs: "Person A" (external dataset/benchmark research) and "Person B" (custom dataset/annotation) — per the `Problem_Statement/` screenshots' handwritten annotations, this maps to team members Smriti and Santosh.
