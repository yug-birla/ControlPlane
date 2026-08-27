# ControlPlane.ai — Current State

**Last updated:** 2026-08-28
**Context:** Accenture Innovation Challenge 2026, Round 2 — Prototype Development (Problem Track 1, "ControlPlane.ai"). See `Problem_Statement/` for the original brief (partially captured as screenshots; not yet transcribed to text — see `BLOCKERS.md`).

## What Exists

**Documentation:**
- `PRODUCT_THESIS_UPDATED.md`, `README.md` — README now mentions `GROQ_MODEL_FAST`/`GROQ_MODEL_STRONG`.
- `docs/architecture/` (10 files), `docs/specs/` (4 files), `docs/DATA/` (14 files + 1 JSON) — unchanged this milestone.
- `docs/ALGORITHMS/` — Milestone 1/2's 5 files plus 3 new: `EXECUTION_GRAPH.md`, `CAPABILITY_ROUTER.md`, `MODEL_ROUTER.md`.
- `docs/EVALUATION/` — Milestone 2's files (updated with new findings) plus 2 new: `ROUTING_RESULTS.md`, `EXECUTION_GRAPH_RESULTS.md`.
- `docs/PROJECT_STATE/` — this folder.

**Data:** unchanged inventory; `query_profiles_validation` (28 examples) now also backs the Capability Router / Model Router evaluations.

**Application code (Milestone 3 — Adaptive Execution, complete 2026-08-28):**
- **New packages:** `controlplane/execution/` (`ExecutionGraph`, `NodeStatus`, `GraphExecutor` — bounded-concurrency wave scheduling), `controlplane/routing/` (`CapabilityRouter`, `ModelRouter`).
- **`controlplane/models/registry.py` extended:** `get_configured_provider(settings, role="FAST"|"STRONG")` and `resolve_model_name(...)` — `GROQ_MODEL_FAST`/`GROQ_MODEL_STRONG` env vars, falling back to `GROQ_MODEL`. `registry_seed.py` now seeds 4 `model_registry` rows (was 2): local embedding, generic Groq, `groq_fast_role`, `groq_strong_role`.
- **`controlplane/runtime.py` rewritten:** after Risk Profiler + Policy, the Capability Router builds an `ExecutionGraph` (parallel data-fetch nodes → merge → generation → optional agent action, filtered by policy restrictions) and the Model Router decides `USE_FAST_MODEL`/`USE_STRONG_MODEL`/`HUMAN_REVIEW`/`ABSTAIN`. The `GraphExecutor` then runs the graph; the `"generation"` node is the only one with a real handler (invokes the routed-role model provider) — every other capability runs via an explicit `MOCKED` handler (no real SQL/RAG/Agent implementation exists yet). `ABSTAIN` skips generation entirely (answer=`None`) rather than risk misrepresenting an unauthorized agentic action.
- **New Postgres table** (migration `8038ec63a9b9`): `route_decisions` — persists every Capability Router + Model Router decision (selected/restricted capabilities, the executed graph, model action/role/verification flags, human-readable reasons).
- **New events:** `PLAN_CREATED`, `ROUTE_STARTED`, `ROUTE_COMPLETED`, `HUMAN_REVIEW_REQUIRED` (all already named in `docs/architecture/EVENT_MODEL.md`'s canonical taxonomy — first implemented here).
- **A real fix to a documented Milestone 2 gap:** `controlplane/risk/baseline.py` now catches the exact governance/decision-support HIGH_RISK case (`QP-190`) that Milestone 2 missed, via a narrowly-scoped trigger (governance/compliance keyword + decision-oriented `intent`) — verified to affect only that one example among the 28-record validation set, with a permanent regression test. See `docs/EVALUATION/RISK_PROFILER_RESULTS.md`.
- **A new false positive discovered (not fixed) during this milestone's routing evaluation:** `QP-198` — a pre-existing sensitivity-classification error (unrelated to the risk fix above) causes a `CRITICAL` misclassification; the system fails *safely* (over-restricts `SQL`, still generates a draft answer under mandatory human review) rather than unsafely. Documented, not patched reactively.
- **A reproducibility finding:** the embedding k-NN-dependent Query Profiler/Risk Profiler metrics do not reproduce exactly across sessions in this environment (rules-only metrics do, bit-for-bit) — most likely a `torch`/`sentence-transformers` environment difference between sessions, not code or per-run randomness (verified stable across repeated same-session runs, including single-threaded BLAS). See both `docs/EVALUATION/QUERY_PROFILER_RESULTS.md` and `RISK_PROFILER_RESULTS.md`.
- **Real measured results, not fabricated** (see `docs/EVALUATION/ROUTING_RESULTS.md`, `EXECUTION_GRAPH_RESULTS.md`): Capability Router produces a structurally valid graph for 28/28 validation examples; Model Router's safety invariant (no HIGH_RISK+ example reaches an unverified fast path) passes against both predicted and ground-truth risk; parallel graph execution measured at 1.96x speedup over sequential on a simulated 2-branch graph (SQL/RAG have no real implementation, so this benchmarks the executor's own concurrency, not real capability latency); 17/28 (60.7%) of validation queries route to FAST instead of unconditionally STRONG.
- **Manual end-to-end verification** (not just unit tests): simple factual → FAST/single-node graph; SQL+RAG-hinted query → parallel data nodes → merge → generation, all real trajectory/event data inspected; the fixed HIGH_RISK governance case → `HUMAN_REVIEW`/STRONG/verification/draft answer generated; an agentic+refund HIGH_RISK query → `AGENT` restricted → `ABSTAIN` (no answer, no misrepresented action); a model-provider failure → correct `route:generation` FAILED step, no duplicate/mislabeled trajectory step; the CRITICAL false-positive (`QP-198`) → `SQL` restricted, `HUMAN_REVIEW`, draft still generated (fails safe, not unsafe).
- `tests/` — 111 automated tests (up from 80), all passing, all DB-backed with no live external API dependency.
- **Explicitly not implemented** (by design): real SQL/RAG/WEB/CHAT_HISTORY/MEMORY/AGENT capabilities (Layer 5/11/18), local generative model pool (Qwen3 tier), multi-provider model routing, cascading/confidence-aware adaptive compute, RAG, evaluators, Intervention Engine, Replanner, Behavioral Drift, Shadow Mode, fine-tuning of anything.

**What does NOT exist:**
- No root-level `AGENTS.md` (see `BLOCKERS.md` B1) — unchanged.
- No single `docs/ARCHITECTURE.md` file (see `BLOCKERS.md` B2) — unchanged.
- Redis and Qdrant remain unused placeholders.
- No plan/plan_version concept beyond the single `PLAN_CREATED` event this milestone emits — no replanning, no plan versioning yet.
- No live Groq comparison result (harness exists, not run this session — same as Milestones 1-2; still `NOT_MEASURED`).

## Phase

**Milestone 3 (Adaptive Execution — Execution Graph, Capability Router, Model Router) complete.** Sequence: documentation audit (`4ae6a76`) -> Layer 0 audit (`ac2f243`) -> Layer 1 Foundation (`008231e`) -> Milestone 1 (`463979e`) -> Milestone 2 (`d396acb`) -> Milestone 3, each explicitly authorized before starting. Awaiting explicit instruction before continuing — see `FUTURE_WORK.md` for candidates (RAG, Response Evaluation, Decision Engine/Intervention/Replanning, Agent Governance, per the bootstrap's own Milestone 4-9 roadmap).
