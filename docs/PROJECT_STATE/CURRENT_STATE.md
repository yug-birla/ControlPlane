# ControlPlane.ai — Current State

**Last updated:** 2026-08-28 (Milestone 6)
**Context:** Accenture Innovation Challenge 2026, Round 2 — Prototype Development (Problem Track 1, "ControlPlane.ai"). See `Problem_Statement/` for the original brief (partially captured as screenshots; not yet transcribed to text — see `BLOCKERS.md`).

## What Exists

**Documentation:**
- `docs/ALGORITHMS/` — 12 prior files plus 3 new: `LLM_JUDGE.md`, `AGENT_GOVERNANCE.md`, `TRUST_LAYER.md`. `RAG_PIPELINE.md`, `EVALUATION_LAYER.md`, `CONTROL_LOOP.md` updated for the reranker, Reasoning upgrade, and CONFLICTING-evidence handling.
- `docs/EVALUATION/` — 3 new: `EVALUATOR_RESULTS.md`, `AGENT_GOVERNANCE_RESULTS.md`, `TRUST_RESULTS.md`. `RAG_RESULTS.md`, `CONTROL_LOOP_RESULTS.md`, `README.md` updated.
- `docs/PROJECT_STATE/` — this folder, updated.

**Application code (Milestone 6 — Cross-Encoder Reranker + LLM Judge + Reasoning/Bias Evaluators + Agent Governance + Trust Layer + Conflicting-Evidence Handling — complete 2026-08-28):**

- **New packages:** `controlplane/judge/` (Local Judge — Qwen2.5-1.5B-Instruct — and Remote Judge — Gemini — sharing one structured-output contract), `controlplane/trust/` (derived HIGH/MEDIUM/LOW trust verdict), `controlplane/governance/` (standalone Agent/Tool gate).
- **`controlplane/rag/` extended:** `reranker.py` — a real cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`, already cached locally), wired live into `RAGCapability` (`use_reranker=True` by default). `adequacy.py`'s `CONFLICTING` check fixed (word-boundary matching, was a real false-positive bug).
- **`controlplane/evaluation/` extended:** `ReasoningEvaluator` upgraded from `NOT_IMPLEMENTED` to a real (narrow) deterministic self-contradiction check; `RAGAdequacyPassthroughEvaluator` added (surfaces `CONFLICTING` to the Decision Engine); `bias.py` (standalone comparative `BiasEvaluator`); `judge_evaluators.py` (`JudgeBackedEvaluator`, real but not in the live default suite).
- **`controlplane/decision/engine.py` extended:** a new `rag_adequacy=CONFLICTING` branch — `RETRIEVE_MORE` while budget remains, else `ASK_CLARIFICATION` (never silently picks one disputed value).
- **`controlplane/runtime.py` extended:** computes `TrustEngine.assess(...)` after Verification; `EvaluationContext` gained `rag_adequacy`; `build_default_runtime`/`Runtime.__init__` gained `rag_capability`/`trust_engine` injection points (used by the new conflicting-evidence test).
- **`controlplane/dashboard/` extended:** a Trust panel (derived, not stored, in the per-request detail view).
- **No new DB tables/migrations this milestone** — Trust is derived (not persisted, a deliberate decision, see `DECISIONS.md`); Judge/Agent-Governance/Bias are evaluated via the existing experiment-tracking tables, not new per-request tables.
- **Local models added:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (already cached, no download) and `Qwen/Qwen2.5-1.5B-Instruct` (tokenizer was already partially staged; full ~3GB weights downloaded this milestone, pinned revision).
- **Three real bugs found and fixed, not assumed away:** (1) the Local Judge's JSON prompt template had a doubled-brace formatting bug causing every call to fail parsing; (2) `AutoModelForCausalLM.from_pretrained` raised a real Windows `OSError: paging file is too small` on default settings, fixed with explicit `dtype=torch.bfloat16`; (3) the RAG adequacy `CONFLICTING` check's naive substring match flagged two unrelated documents as conflicting because "not" matched inside "notice" — found via a real end-to-end regression at a widened retry `k`, same root-cause class as Milestone 3's actionability false-positive, fixed with word-boundary matching.
- **Real, measured results:** reranker comparison (dense/fusion/cross-encoder: recall@1 0.962→0.962→1.000, MRR 0.981→0.981→1.000, cross-encoder costs ~1.1s/query vs ~44ms); judge calibration (deterministic 1.0/1.0 accuracy/F1 vs. Local Judge 0.95/0.95 on a 20-case derived grounding benchmark — the judge does not beat the baseline on this easy set, reported honestly); Agent Governance gate (0.72 accuracy, 0.756 macro-F1, perfect on the safety-critical BLOCK/HUMAN_REVIEW classes) against 75 real trajectory labels.
- `tests/` — 222 automated tests (up from 186), all passing, all DB-backed except pure-logic modules, no live external API dependency.
- **Explicitly not implemented / deferred:** Behavioral Drift, Permission Lineage, Partial Execution states, Shadow Mode (Layers 19-20 — no existing real data to ground them, unlike Agent Governance); the Agent Governance gate is real but not wired into any live execution path (the `AGENT` capability itself is still `MOCKED`); Remote Judge (Gemini) not live-validated this session (no key); a local generative model pool distinct from the judge; fine-tuning of anything.

**What does NOT exist:**
- No root-level `AGENTS.md` (`BLOCKERS.md` B1) — unchanged.
- No single `docs/ARCHITECTURE.md` file (`BLOCKERS.md` B2) — unchanged.
- Redis and Qdrant remain unused placeholders.
- No live agent/tool execution (Layer 5's `AGENT` capability is still `MOCKED`), so the new governance gate has nothing live to gate yet.
- No Behavioral Drift (Layer 19), no Shadow Mode (Layer 20).
- No live Groq-vs-Gemini benchmark at scale, and no live Gemini validation at all this session (no API key present).

## Phase

**Milestone 6 (Cross-Encoder Reranker + LLM Judge + Reasoning/Bias Evaluators + Agent Governance + Trust Layer + Conflicting-Evidence Handling) complete.** Sequence: documentation audit (`4ae6a76`) → Layer 0 (`ac2f243`) → Layer 1 (`008231e`) → Milestone 1 (`463979e`) → Milestone 2 (`d396acb`) → Milestone 3 (`ba4896e`) → Milestones 4+5 (`7dc76a9`) → Milestone 6 (this commit). Awaiting explicit instruction before continuing — see `FUTURE_WORK.md`.
