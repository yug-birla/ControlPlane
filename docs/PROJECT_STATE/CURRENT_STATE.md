# ControlPlane.ai — Current State

**Last updated:** 2026-08-28
**Context:** Accenture Innovation Challenge 2026, Round 2 — Prototype Development (Problem Track 1, "ControlPlane.ai"). See `Problem_Statement/` for the original brief (partially captured as screenshots; not yet transcribed to text — see `BLOCKERS.md`).

## What Exists

**Documentation:**
- `PRODUCT_THESIS_UPDATED.md`, `README.md` — updated with Gemini env vars, SQLite setup step, dashboard pointer.
- `docs/architecture/`, `docs/specs/`, `docs/DATA/` — unchanged this milestone.
- `docs/ALGORITHMS/` — 8 prior files plus 6 new: `RAG_PIPELINE.md`, `SQL_CAPABILITY.md`, `EVALUATION_LAYER.md`, `CONTROL_LOOP.md` (Decision+Intervention+Replanner+Verification together), `MODEL_PROVIDER_ABSTRACTION.md` (updated §17 for Gemini).
- `docs/EVALUATION/` — 2 new: `RAG_RESULTS.md`, `CONTROL_LOOP_RESULTS.md`.
- `docs/PROJECT_STATE/` — this folder.

**Application code (Milestones 4+5 together — Real RAG/SQL/Evaluation/Gemini/Dashboard, then Decision/Intervention/Replan/Verification — complete 2026-08-28):**

- **New packages:** `controlplane/rag/` (ingestion, dense+BM25+fusion retrieval, adequacy), `controlplane/capabilities/` (real SQL — SQLite/NexaConsult, template-matched, read-only; real RAG), `controlplane/evaluation/` (6 real evaluators + 2 honest `NOT_IMPLEMENTED`), `controlplane/decision/` (policy-matrix Decision Engine), `controlplane/intervention/` (Intervention Engine), `controlplane/verification/` (Verification Engine), `controlplane/dashboard/` (read-only observability UI).
- **`controlplane/models/` extended:** `gemini_provider.py` (real, live-validated, comparison-only — never the Model Router's default), `embedding_cache.py` (the B9 fix, shared by the Query Profiler and RAG).
- **`controlplane/runtime.py` rewritten again:** after generation + evaluation, `_run_control_loop` runs Decide → (Intervene → Replan → re-Evaluate)* → Verify, bounded to one retry (`max_attempts=2`). New DB tables: `response_evaluations`, `decisions`, `interventions`, `replans`, `verifications`; `route_decisions` gained `plan_version`.
- **A CRITICAL bug found and fixed this milestone:** through Milestone 4, the model's prompt never actually included retrieved SQL/RAG evidence (`provider.generate(prompt=query)` used the raw query only) — SQL/RAG ran, were evaluated, and were persisted, but never actually influenced a real generated answer. Fixed in `_build_generation_prompt`. Verified via manual trace and now covered by the real end-to-end control-loop tests.
- **Two more real bugs found via manual/test validation, not assumed away:** `FactualityEvaluator` originally checked SQL rows only, flagging a correct RAG-sourced number as "CONTRADICTED"; `RAGCapability.execute()` didn't accept the `k` override the Intervention Engine's RETRIEVE_MORE mechanism needed (would have crashed every RAG self-healing attempt) — both fixed, both regression-tested.
- **A semantic actionability false-positive found and fixed:** "the refund policy document" (a topic reference) was misclassified as an agentic action request purely from keyword presence — fixed with a syntactic-position check (not another exception keyword), root-caused per the error-driven-development checklist as a weak-algorithm issue, not bad data.
- **B9 (reproducibility) fixed, not just characterized:** embeddings are now disk-cached and committed (`data/cache/*.npz`) — k-NN-dependent metrics reproduce identically across sessions regardless of installed library version. Dependency versions also pinned in `pyproject.toml` as a secondary measure.
- **Real, measured self-healing:** the RAG self-healing, model-escalation, and high-risk-control scenarios all pass as permanent end-to-end tests using scripted (not live) model responses, with genuine re-execution (a second real model call, a second real retrieval) — see `docs/EVALUATION/CONTROL_LOOP_RESULTS.md`. Before/after counterfactual: 3/5 scenarios intervened, 2/5 improved, 1/5 safely abstained, 0/5 unnecessary interventions.
- **N+1 dashboard query bug found and fixed** during the mandatory architecture audit (a test run took 101s; root-caused to 2 extra queries per listed request).
- `tests/` — 186 automated tests (up from 111), all passing, all DB-backed, no live external API dependency (both Groq and Gemini are always faked in automated tests; each has one manual live-check script).
- **Explicitly not implemented / deferred:** Reasoning and Bias evaluators (honest `NOT_IMPLEMENTED`), a semantic/cross-encoder RAG reranker, multi-provider Model Routing, a local generative model pool, LLM-based query reformulation for RETRIEVE_MORE, public dataset expansion (existing `rag_cases.json`/`query_profiles` data was sufficient for everything measured this milestone), fine-tuning of anything (no measured gap justifies it yet).

**What does NOT exist:**
- No root-level `AGENTS.md` (`BLOCKERS.md` B1) — unchanged.
- No single `docs/ARCHITECTURE.md` file (`BLOCKERS.md` B2) — unchanged.
- Redis and Qdrant remain unused placeholders.
- No Agent/Tool governance (Layer 18), no Behavioral Drift (Layer 19), no Shadow Mode (Layer 20).
- No live Groq-vs-Gemini benchmark at scale (a small, deliberate 3-query sample was run live this session; a larger comparison is future work, gated on quota).

## Phase

**Milestones 4 (Real RAG + SQL + Evaluation + Gemini + Dashboard) and 5 (Decision + Intervention + Replan + Verification) complete, committed together** (Milestone 4 was never separately committed before Milestone 5's work began, per the continuing session's own instruction to treat the mandatory architecture audit as covering both). Sequence: documentation audit (`4ae6a76`) → Layer 0 (`ac2f243`) → Layer 1 (`008231e`) → Milestone 1 (`463979e`) → Milestone 2 (`d396acb`) → Milestone 3 (`ba4896e`) → Milestones 4+5 (this commit). Awaiting explicit instruction before continuing — see `FUTURE_WORK.md`.
