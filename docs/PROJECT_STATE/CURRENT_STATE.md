# ControlPlane.ai — Current State

**Last updated:** 2026-08-28
**Context:** Accenture Innovation Challenge 2026, Round 2 — Prototype Development (Problem Track 1, "ControlPlane.ai"). See `Problem_Statement/` for the original brief (partially captured as screenshots; not yet transcribed to text — see `BLOCKERS.md`).

## What Exists

**Documentation:**
- `PRODUCT_THESIS_UPDATED.md`, `README.md` — README now documents the full local-model setup (CPU-only torch install, model download, registry seeding).
- `docs/architecture/` (10 files) — `TRAJECTORY_AND_LEDGER.md` and `EVENT_MODEL.md` carry "Implementation status" notes.
- `docs/specs/` (4 files) — unchanged, still design-only.
- `docs/DATA/` (14 files + 1 JSON) — unchanged this milestone.
- `docs/ALGORITHMS/` — Milestone 1's 2 files plus 3 new: `LOCAL_EMBEDDING_MODEL.md`, `QUERY_PROFILER_BASELINE.md`, `RISK_PROFILER_BASELINE.md`.
- `docs/EVALUATION/` (new, 2026-08-28) — `README.md`, `DATASETS.md`, `QUERY_PROFILER_RESULTS.md`, `RISK_PROFILER_RESULTS.md`, `MODEL_BENCHMARKS.md`, `RESULTS/` (raw JSON per run).
- `docs/PROJECT_STATE/` — this folder.

**Data:** unchanged inventory; the query-profile dataset (train/validation splits) is now actually consumed — as the k-NN exemplar bank and as evaluation ground truth (see `docs/EVALUATION/`).

**Application code (Milestone 2 — Query Intelligence + Risk Baseline + Local HF Models + Experiment Tracking, complete 2026-08-28):**
- **New packages:** `controlplane/query_intelligence/` (Query Profiler: rules baseline, embedding k-NN baseline, hybrid combiner), `controlplane/risk/` (Risk Profiler baseline, 9 dimensions), `controlplane/policy/` (baseline policy tiers), `controlplane/experiments/` (experiment/evaluation tracking + 4 runnable evaluation scripts).
- **`controlplane/models/` extended:** `embedding_provider.py` (a separate ABC from `ModelProvider`, deliberately — see `DECISIONS.md`), `local_hf_provider.py` (`LocalHFEmbeddingProvider`, offline-first), `model_download.py` (setup-time download), `registry_seed.py`.
- **Local model:** `sentence-transformers/all-MiniLM-L6-v2` @ pinned revision, verified live against the HF API (not recalled from training data), downloaded and cached, offline-load verified. Hardware inspected first (CPU-only machine, 15.7GB RAM, no GPU) before selecting it — see `docs/ALGORITHMS/LOCAL_EMBEDDING_MODEL.md`.
- **`controlplane/runtime.py` extended:** the flow now includes Query Profiler -> `QUERY_PROFILED` event -> Risk Profiler + Policy -> `RISK_DETECTED` event, persisting a real `query_profiles` row per request, before the (unchanged) model invocation step. `EventType` gained `QUERY_PROFILED`/`RISK_DETECTED` (both already named in `docs/architecture/RUNTIME_FLOW.md`'s canonical list — first implemented here, not invented).
- **New Postgres tables** (migration `601a04e04640`): `query_profiles`, `model_registry` (extended beyond the original `docs/DATA/POSTGRES_SCHEMA.md` §5.2 fields), `experiments`, `experiment_runs`, `evaluation_results`, `model_benchmarks`.
- **Real bugs found and fixed during this milestone** (not just features added): (1) the embedding provider was reloading the model from disk on every single profiling call — fixed with `@lru_cache`; (2) the Hybrid profiler's "trust the rule" logic couldn't distinguish a confident keyword match from a rule's own generic fallback default (e.g. word-count-based complexity), so it never actually deferred to the k-NN baseline for those fields — fixed by adding an explicit `high_confidence_fields` marker, only set on real trigger matches; (3) a copy-paste bug had the `impact` field checking the `"intent"` confidence key instead of `"impact"`.
- **Real measured results, not fabricated** (see `docs/EVALUATION/`): Query Profiler accuracy 35.7-85.7% depending on field (complexity is near chance-level — flagged prominently, not hidden); Risk Profiler missed its one true HIGH_RISK validation example (a governance/decision-support case with no agentic action) — a genuine, documented failure mode; local embedding latency p50=16ms/p95=32ms/p99=47ms warm, ~20s cold start; local-vs-remote Groq comparison harness built and run, remote side correctly marked `NOT_MEASURED` (no `GROQ_API_KEY` available in this session — never fabricated).
- **Manual end-to-end verification**, all 8 required query types (public factual, enterprise factual, RAG-intent, SQL-intent, reasoning, high-impact action, ambiguous, sensitive/privacy) — outputs actually inspected, not assumed correct. Notably: the high-impact-action query correctly reached `HIGH_RISK`/`human_approval_required=True`/`AGENT` restricted; the sensitive/PII query reached only `MEDIUM_RISK` and did *not* escalate to `DEEP_PATH` (severity-gated, not dimension-gated — a documented design choice, not a bug, but worth revisiting).
- `tests/` — 80 automated tests (up from 45), all passing, all DB-backed with no live external API dependency (local model must be cached first; Groq calls are always faked in automated tests).
- **Explicitly not implemented** (by design): capability/model routing (route hints are informational only), RAG, evaluators, Intervention Engine, Replanner, Behavioral Drift, Shadow Mode, fine-tuning of anything.

**What does NOT exist:**
- No root-level `AGENTS.md` (see `BLOCKERS.md` B1) — unchanged.
- No single `docs/ARCHITECTURE.md` file (see `BLOCKERS.md` B2) — unchanged.
- Redis and Qdrant remain unused placeholders.
- No plan/plan_version concept, no `PLAN_CREATED` event (nothing plans yet).
- No live Groq comparison result (harness exists, not run this session — see `docs/EVALUATION/MODEL_BENCHMARKS.md`).

## Phase

**Milestone 2 (Query Intelligence + Risk Baseline + Local HF Models + Experiment Tracking) complete.** Sequence: documentation audit (`4ae6a76`) -> Layer 0 audit (`ac2f243`) -> Layer 1 Foundation (`008231e`) -> Milestone 1 (`463979e`) -> Milestone 2, each explicitly authorized before starting. Awaiting explicit instruction before continuing — see `FUTURE_WORK.md` for candidates.
