# ControlPlane.ai — Current State

**Last updated:** 2026-08-30 (Milestone 16)
**Context:** Accenture Innovation Challenge 2026, Round 2 — Prototype Development (Problem Track 1, "ControlPlane.ai"). See `Problem_Statement/` for the original brief (partially captured as screenshots; not yet transcribed to text — see `BLOCKERS.md`).

## What Exists

### Milestone 16 (2026-08-30) — the "measured nothing" milestone

Four independent components were **implemented, runtime-wired, tested, and reporting a structurally impossible value.** None failed. None broke a test. Each was found by reading recorded output and asking whether the number could be right.

| Component | What it reported | What was wrong |
|---|---|---|
| Trajectory latency | `latency_ms_p50: null` for **every** component | `completed_at` set before flush, `started_at` defaulted at flush — 298/400 steps had non-positive spans, one finishing 1ms before it started |
| MCP evidence count | `0` for every RAG operation across 157 steps | Adapter read `output["chunks"]`; `RAGCapability` returns `"evidence"` |
| MCP permissions | `[]` for the most-used capability | RAG declared no `required_permissions` while SQL did |
| MCP events | zero in 3000 consecutive events | No event type existed |
| `DriftLevel.HIGH` | never emitted; precision 0.000, recall 0.000 | Level derived from signal *count*, saturating at MEDIUM |

All fixed, each with a test asserting on a recorded **value** rather than a code path.

**What the latency fix then revealed (§7).** ControlPlane's warm overhead is **~1.8s**, not the 42s a cold run suggests (that is one-time model loading). Mean model calls per request: **1.07**. Latency correlates with **input** tokens (0.559), not output (0.152) — 29.3s at <250 tokens vs 139.3s above 1000. The 2.1× penalty is **prefill of retrieved evidence**, not governance overhead.

**Over-control decomposed (§8).** The 0.304 headline counts three behaviours: withheld a **correct** answer (0.130, the defect), asked for clarification (0.109), and correctly controlled a **wrong** answer (0.065 — the system working, charged as a cost). Root cause of the largest contributor found and fixed: `factuality` flagged numbers **the user supplied in their own question**.

**Multi-agent, measured (§12).** Four conditions, identical queries and model. `key_fact_accuracy` **0.583 in all four** — decomposition changed nothing. Communication (24 messages vs 0) changed nothing: it is currently **observability, not capability**. Parallelism is structurally real but its measured latency benefit is **negligible** (median +2.7% over sequential) -- the 1.84x figure from the first run was outlier distortion and is retracted. The run exposed a **safety gap**: the planner discarded a lone gatherer, so the flagship exfiltration case could not fire (composition risk accuracy 0.000). Fixed.

### Component status after Milestone 16

| Area | Status | Evidence |
|---|---|---|
| Baseline vs ControlPlane | `SERIOUS_BENCHMARK` at 62 cases | key-fact 0.065→0.826, hallucination 0.304→0.043, unsafe control 0→1.000 |
| Latency decomposition | `IMPLEMENTED` + measured | per-component spans now real |
| Prompt-injection detection | `IMPLEMENTED`, domain-aware | enterprise TEST macro-F1 0.899 |
| Factuality | `IMPLEMENTED`, provenance-aware | over-control 4→1, 0 missed fabrications |
| Reasoning | `IMPLEMENTED`, numeric layer | held-out macro-F1 0.582, precision 1.000 |
| Behavioral drift | `IMPLEMENTED` v2 | held-out exact 0.800, HIGH f1 0.909 |
| MCP fabric | `IMPLEMENTED`, real access path | SQL+RAG execute through it; events now emitted |
| Multi-agent | `IMPLEMENTED`, **null result for quality** | 0.583 across all conditions |
| Agent communication | `IMPLEMENTED`, **observability only** | C vs D identical on every quality metric |
| Prometheus judge | `NOT_MEASURED` | never run to completion |
| Model routing benchmark | `NOT_MEASURED` | ALWAYS-FAST / ALWAYS-STRONG / ADAPTIVE not run |
| Dashboard | `IMPLEMENTED`, verified live | `/dashboard`, `/evidence`, `/datasets`, `/health-map` |

**Dataset health, counted from the files:** 21 datasets, 1,796 cases, **3 with a held-out split**, 19 carrying at least one warning. Visible at `/dashboard/datasets`.

`tests/` — **482 automated tests**, all passing.



**Documentation:**
- `docs/ALGORITHMS/` — 17 prior files plus 2 new: `CORPUS_AFFINITY_ROUTING.md`, `SHADOW_MODE.md`.
- `docs/EVALUATION/` — 1 new: `BASELINE_VS_CONTROLPLANE.md` (the central product experiment, its methodology, its results, and the two bugs found in the harness itself).
- `docs/DATA/` — `EXTERNAL_DATASETS.md` (Milestone 8). New dataset this milestone: `data/raw/generated/baseline_vs_controlplane_cases.json` (26 cases, provenance HUMAN).
- `docs/PROJECT_STATE/` — this folder, updated.

**Application code (Milestones 11-13 — Adaptive Compute, MCP Fabric, Multi-Agent Runtime, Visual Dashboard, Corpus Expansion):**

- **Adaptive compute runtime-wired** (`controlplane/routing/adaptive_compute.py` + `model_performance.py`): decides `STOP`/`SELF_REFINE`/`ESCALATE` *after* execution. Escalation must clear an evidence bar from observed model performance; on this project it currently does **not**, so the cheaper same-model refinement runs instead. The belief lives in data, not code.
- **MCP capability fabric** (`controlplane/mcp/`): discovery, invocation, normalized results, the specified failure taxonomy, health that degrades on observed failure. Labelled `IN_PROCESS`, not a networked deployment. "MCP must never become the brain" is enforced **structurally** — a test parses the AST of every module and fails if any imports decision/policy/risk/trust/routing.
- **Multi-agent planning + execution + communication**: the planner derives agent count from measured data requirements (0 agents for a single-source read, 3 for an agentic multi-source task). Gatherer agents are governed wrappers around real capabilities. Every agent message is an `AGENT_MESSAGE_SENT` event; a `REPLAN_REQUEST` is **triaged, not obeyed**, and triage is grounded in what the agent *did* rather than how its message reads.
- **Visual dashboard, verified running**: execution map derived from real persisted execution (never a static diagram), failure localization, component diagnostics, MCP view, agent communication, plan evolution, system-wide component health. Served at `http://127.0.0.1:8000/dashboard`.
- **Evaluation corpus expanded**: primary benchmark **26 → 62 cases** across 10 categories with every grounded label verified against the corpus; bias **8 → 24 pairs** across 15 dimensions.
- `tests/` — **410 automated tests**, all passing.

**Four defects found by running the real system, not by tests:**
1. Gatherer agents produced **no evidence** — collectors keyed on `capability == "RAG"` while a gatherer's capability is `"AGENT"`. The model answered "I don't have direct access to external databases" and the request was still **VERIFIED with trust HIGH**, because grounding was `NOT_APPLICABLE` rather than `UNSUPPORTED`.
2. Gatherer agents **duplicated** retrieval alongside plain data nodes.
3. A gatherer's synthesized tool name matched nothing in the composition governor's tables, so an agent reading the enterprise DB scored `PUBLIC` — **the exfiltration path would not have fired**.
4. Component health reported a confident **p50 of 0.0ms** for every component — an artefact of when trajectory rows are written, not a measurement.

**Application code (Milestone 10 — Component Diagnostics, Dynamic Planning, Multi-Tier Models, Multi-Agent Governance, Prometheus Judge — IN PROGRESS 2026-08-29):**

- **`controlplane/diagnostics/` (NEW):** component-level state + **failure localization** — answers *which* component failed, not just that the request failed. A derived view over already-persisted data (no new table). Correctly attributes an ungrounded answer with no retrieval to **routing**, not generation — which is exactly what let the Milestone 9 bug hide behind "every component completed successfully". Governed hostile input is reported as `INPUT_GOVERNED`, never as a component defect.
- **`controlplane/capabilities/registry.py` (NEW):** Capability Registry — centralized metadata (status, side-effect level, satisfied data requirements, permissions, cost/latency/risk). Status is never more optimistic than reality: `CHAT_HISTORY`/`MEMORY`/`WEB` are registered `MOCKED` because they run via the placeholder handler.
- **`controlplane/planning/replanner.py` (NEW):** **dynamic, graph-mutating replanning.** A replan previously bumped `plan_version` and re-ran the same node with a wider `k` — the graph never changed. Now verified end-to-end as a real `PLAN V1 (data_rag) → PLAN V2 (data_rag + data_sql)` mutation, with the added capability selected by registry lookup against the query's own data requirements (not a hard-coded rule), and skipped for CONFLICTING evidence.
- **`controlplane/governance/multi_agent.py` (NEW):** multi-agent composition governance, **runtime-wired**. Catches chains that are individually safe but collectively unsafe (agent A reads confidential data → ALLOW; agent B sends externally → ALLOW; the composition is an exfiltration path). `AgentGate` evaluates one step and structurally cannot see this.
- **Real multi-tier model routing:** FAST = Qwen2.5-1.5B, STRONG = Qwen3-4B (the exact tier the architecture doc names; revision verified against the live HF API). `enable_thinking=False` prevents Qwen3's `<think>` blocks from being persisted, per the no-stored-CoT rule.
- **`controlplane/judge/prometheus_judge.py` (NEW):** Prometheus 2 (7B) judge using the model's own absolute-grading template, mapped back onto the existing `JudgeResult` contract. **Blocked on hardware** — see `BLOCKERS.md` B12.
- **Two real bugs found by running diagnostics against real persisted data:** `route_decisions.execution_graph` was written *before* execution, so every node status in the DB was frozen at `PENDING` since Milestone 3; and list-valued profile fields stored as `{"values": [...]}` were iterated as dict keys.
- **An honest negative result:** the STRONG tier (Qwen3-4B) is **not** better than FAST on the tier benchmark (0.800 vs 0.900), at ~2.5x the per-token cost. This corrected an overstated claim in an earlier commit of this same milestone. Model escalation is demonstrated to **change the model, not to improve quality** — see `docs/EVALUATION/MODEL_TIER_RESULTS.md`.
- `tests/` — 335 automated tests (up from 304), all passing.
- **Not started this milestone:** MCP capability fabric (§39–§59), chat-history dataset/capability, dataset expansion, multi-agent *planning* (the default router still emits at most one AGENT node — composition governance is real, composition planning is not).

**Application code (Milestone 9 — Local Generative Model, Corpus-Affinity Routing, Shadow Mode, Baseline-vs-ControlPlane Evidence — complete 2026-08-29):**

- **`controlplane/models/local_generation_provider.py` + `local_llm.py` (NEW):** a real offline generative `ModelProvider` (Qwen2.5-1.5B-Instruct, CPU). Closes a P0 gap: with only key-gated Groq/Gemini and no key in any session since Milestone 2, the runtime had **no generative model**, so every end-to-end scenario and the central product claim ran on scripted fakes. `LocalJudge` was refactored onto the shared loader rather than duplicating its configuration.
- **`controlplane/query_intelligence/corpus_affinity.py` (NEW):** semantic RAG routing. Fixes the milestone's biggest finding — the deployed profiler retrieved on only **10/19 = 0.526** of corpus-answerable questions (the keyword rule alone: 1/19 = 0.053), so ControlPlane returned *byte-identical answers to an unmanaged model* on the cases it missed. End-to-end retrieval rate **0.526 → 1.000**; keyword-vs-affinity held-out routing F1 **0.100 → 0.947**. Threshold 0.41, calibrated on data disjoint from the reporting set.
- **`controlplane/governance/shadow_mode.py` (NEW):** Shadow Mode — a specified-architecture gap `NOT_IMPLEMENTED` since Milestone 6, with zero prior references in the codebase. Observes and records `WOULD_*` verdicts (derived from the real Decision Engine, not reimplemented) while suppressing every consequence. Wired into `Runtime`/`build_default_runtime`, new `SHADOW_DECISION_RECORDED` event, 3 end-to-end scenarios.
- **`controlplane/experiments/evaluate_baseline_vs_controlplane.py` + `evaluate_ablations.py` + `rescore_results.py` (NEW):** the central product experiment on real model output, plus component ablations and a deterministic re-scoring tool.
- **Actionability over-control fixed:** informational threshold questions ("Above what wire transfer amount is dual authorization required?") were escalated to `HIGH_RISK` human review. Fixed with a conjunctive grammatical guard, regression-tested in **both** directions so a genuine action request can never be demoted.
- **THE CENTRAL RESULT** (26 hand-authored cases, real local model, identical scoring, `DEVELOPMENT_TEST` scale): key-fact accuracy **0.105 → 0.947**, hallucination rate **0.316 → 0.000**, grounding supported **0.000 → 0.895**, appropriate abstention **0.500 → 1.000**, control on unsafe cases **0.000 → 1.000**; costs: over-control on benign cases 0.263 (pre-fix) and +40% latency.
- **Two bugs found in the measurement harness itself**, both of which had been *understating* ControlPlane — found by reading per-case rows rather than trusting aggregates, fixed, regression-tested, and results re-scored deterministically from saved answers without re-running inference.
- `tests/` — 281+ automated tests (up from 259), all passing.

**Application code (Milestone 8 — E: Drive Migration, Judge Few-Shot, Real Public Injection Dataset + Embedding k-NN Detector, RRF Architecture Compliance — complete 2026-08-28):**

- **`BLOCKERS.md` B10 actually fixed, not just documented:** the entire ~8.6GB Hugging Face cache moved from `C:\Users\Lenovo\.cache\huggingface` to `E:\ControlPlane\.cache\huggingface`; `HF_HOME`/`HF_HUB_CACHE`/`TRANSFORMERS_CACHE` set persistently via `setx`. Reclaimed ~9GB on C: (11GB→20GB free). Verified all 3 local models still load offline afterward. Full test suite now runs in ~52-55s, matching the pre-B10 healthy baseline (down from the 76-minute anomaly).
- **Judge few-shot prompting attempted and honestly reported as insufficient:** 3 few-shot examples added to `controlplane/judge/prompts.py`'s grounding prompt (unrelated office-policy domain to avoid test leakage). Real result: accuracy 0.375→0.417, macro-F1 0.300→0.320, but Milestone 7's `PARTIALLY_SUPPORTED` class-collapse (0/24 predictions) was **not** fixed — few-shot only shifted overall bias toward `UNSUPPORTED`. Per the bootstrap's own improvement ladder, model comparison (not fine-tuning) is the next justified step, not attempted this milestone.
- **Real public dataset integrated for prompt-injection detection:** `deepset/prompt-injections` (HuggingFace, Apache-2.0, pinned revision, 662 examples: 546 train + 116 test) normalized into `data/external/deepset_prompt_injections/` with new provenance value `"EXTERNAL"`. Measured against Milestone 7's keyword-only `PromptInjectionEvaluator`: accuracy 0.609, macro-F1 0.392, **false-negative rate 98.5%** (259/263 real injections missed) — the earlier 12-case "1.0 accuracy" benchmark was confirmation bias from fixed phrases, not evidence of generalization.
- **`controlplane/evaluation/injection_knn.py` (NEW):** `EmbeddingKNNInjectionDetector` — reuses the existing local `all-MiniLM-L6-v2` embedding model, k=5 majority vote over TRAIN-split reference embeddings (disk-cached via the B9 pattern), with a `similarity_threshold` reject-option. Real measured improvement on held-out TEST split (no leakage): macro-F1 0.326→0.796. Threshold shipped at a deliberate, documented `0.30` rather than the raw grid-search-optimal `0.20`, trading measured in-domain performance for real-world generalization safety (the raw optimum would still have misclassified a real benign-SQL false positive found during testing).
- **`controlplane/evaluation/evaluators.py`'s `PromptInjectionEvaluator` upgraded to two layers:** keyword-first (free, short-circuits), embedding k-NN fallback only if the keyword layer finds nothing; degrades gracefully if the dataset is missing.
- **RRF (Reciprocal Rank Fusion) adopted as the retrieval fusion default**, replacing min-max weighted-sum fusion — `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` explicitly mandates "Dense + BM25 + RRF + Cross-Encoder" as the source-of-truth pipeline; Milestones 4-7 were an undocumented deviation, found during this milestone's architecture audit. Measured comparison showed **identical** results (recall@1/recall@3/MRR) between RRF and min-max on the 26-case benchmark — a real null finding that removes any measured reason to keep deviating, so the spec's own default is now adopted (`min_max` kept available, not deleted).
- **A real false-positive bug found via end-to-end testing, not a targeted unit test:** the threshold-less k-NN detector flagged a benign SQL query as an injection because majority vote always returns a label regardless of similarity magnitude (all 5 neighbors were near-orthogonal, similarity ~0.2). Fixed with the reject-option threshold above.
- `tests/` — 259 automated tests (up from 253 measured at the start of this milestone), all passing, ~52s wall-clock.
- **`walledai/BBQ` bias dataset investigated but not integrated:** confirmed to exist (CC-BY-4.0) but its multiple-choice QA format doesn't map to the existing pairwise `BiasEvaluator` without substantial adapter work — documented as a deferred candidate.
- **Explicitly not implemented / deferred (unchanged from Milestone 7):** Shadow Mode (Layer 20); Behavioral Drift live-wiring (no real historical volume yet); multi-agent composition tracking; Bias dataset expansion beyond 8 pairs; fine-tuning of anything.

**What does NOT exist:**
- No root-level `AGENTS.md` (`BLOCKERS.md` B1) — unchanged.
- No single `docs/ARCHITECTURE.md` file (`BLOCKERS.md` B2) — unchanged.
- Redis and Qdrant remain unused placeholders.
- ~~No Shadow Mode (Layer 20)~~ — **implemented Milestone 9**.
- No live Groq-vs-Gemini benchmark at scale, and no live Gemini/Groq validation at all this session (no API keys present). The system is now fully runnable offline via the local generative provider.
- No multi-agent composition tracking (specified, still NOT_IMPLEMENTED).
- No judge model-comparison experiment (the justified next step after Milestone 8's few-shot attempt).
- No multi-step agent tool-calling loop (one `AGENT` node per graph) — Behavioral Drift and Permission Lineage are correspondingly single-hop.
- No BBQ (or other public) bias dataset integration yet — investigated, not adapted.
- No local-generative-model comparison for the Judge's `PARTIALLY_SUPPORTED` collapse (the bootstrap's next-justified-step after few-shot).

## Phase

**Milestone 10 in progress** (component diagnostics, dynamic planning, multi-tier models, multi-agent governance, Prometheus judge). **Milestone 9 complete.** Sequence: documentation audit (`4ae6a76`) → Layer 0 (`ac2f243`) → Layer 1 (`008231e`) → Milestone 1 (`463979e`) → Milestone 2 (`d396acb`) → Milestone 3 (`ba4896e`) → Milestones 4+5 (`7dc76a9`) → Milestone 6 (`a543f8c`) → Milestone 7 (`e385ad9`) → Milestone 8 (`5c22e15`) -> Milestone 9 (`c19eafb`) -> Milestone 10 (`8a44d7b`, `7be1f24`, `8576f26`, `b04db58`, `1da687d`). Awaiting explicit instruction before continuing — see `FUTURE_WORK.md`.
