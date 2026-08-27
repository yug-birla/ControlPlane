# ControlPlane.ai — Future Work / Implementation Plan

**Development model changed 2026-08-27 (Milestone 1):** development moved from strict one-layer-at-a-time to milestone-based ("implement tightly coupled architecture components together so every milestone produces real, testable product functionality"). The Layer 0-23 table below is kept as a map of governing docs and is updated as milestones land, but milestones may complete several layers' worth of scope together (Milestone 1 completed Layer 1 fully and most of Layers 2-3, plus a real model invocation that was originally scoped for Layer 10). **Still incremental and still stops after each milestone for explicit instruction** — that rule is unchanged.

| Layer | Name | Status | Governing doc(s) | Notes |
|---|---|---|---|---|
| 0 | Repository / Project Audit | **Done** (2026-08-27) | This folder | See `CURRENT_STATE.md`, `BLOCKERS.md` |
| 1 | Foundation (API entrypoint, request/trace/trajectory IDs, execution state, config, logging, error model, health checks) | **Done** (2026-08-27) | `docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md` §2, §7, §20-21; `docs/architecture/SCALE_ARCHITECTURE_UPDATED.md` | `controlplane/main.py`, `context.py`, `state.py`, `errors.py`, `api/` |
| 2 | Execution State + Trajectory + Ledger | **Done** (2026-08-27, Milestone 1) | `docs/architecture/TRAJECTORY_AND_LEDGER.md`; `docs/DATA/POSTGRES_SCHEMA.md` §3, §9-10 | `controlplane/trajectory/`, `controlplane/ledger/`, real Postgres. Plan/plan_version linkage still absent (needs Layer 4-5) |
| 3 | Event Model | **Partially done** (2026-08-27, Milestone 1) | `docs/architecture/EVENT_MODEL.md` | `controlplane/events/` — 4 of ~29 canonical events implemented (`QUERY_RECEIVED`, `MODEL_CALLED`, `MODEL_FAILURE`, `FINAL_RESPONSE_GENERATED`), in-process transport. Remaining events get added as the components that would emit them are built |
| 4 | Execution Graph | Not started | `docs/architecture/RUNTIME_FLOW.md` §11-12; `PRODUCT_THESIS_UPDATED.md` §8 | |
| 5 | Capability / MCP Fabric | Not started | `PRODUCT_THESIS_UPDATED.md` §11; `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §45 | 5 capability groups: Model, SQL/Data, RAG/Retrieval, Web/External Data, Agent/Tools. `controlplane/models/` is a proof that this pattern (thin interface + one real adapter) works |
| 6 | Synthetic Data Environment | Partially done (data generated, not loaded into Postgres) | `docs/DATA/DATASET_REGISTRY.md`, `docs/DATA/POSTGRES_SCHEMA.md` §12-14 | **Resolve `BLOCKERS.md` B4 first** (two incompatible enterprise datasets) |
| 7 | Baseline Query Intelligence | **Done** (2026-08-28, Milestone 2) | `docs/DATA/SCHEMA.md`; `PRODUCT_THESIS_UPDATED.md` §6; `docs/ALGORITHMS/QUERY_PROFILER_BASELINE.md` | `controlplane/query_intelligence/`. Complexity classification needs rework (near chance-level) before anything gates on it — see `docs/EVALUATION/QUERY_PROFILER_RESULTS.md` |
| 8 | Baseline Risk / Policy | **Done** (2026-08-28, Milestone 2) | `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md`; `docs/ALGORITHMS/RISK_PROFILER_BASELINE.md` | `controlplane/risk/`, `controlplane/policy/`. Missed its one true HIGH_RISK validation example (governance/decision-support, no agentic action) — see `docs/EVALUATION/RISK_PROFILER_RESULTS.md` before trusting for anything safety-critical unassisted |
| 9 | Data / Capability Routing | Not started (inputs now exist) | `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` (Capability Router) | `QueryFingerprint.capability_hints`/`data_requirement` are the intended input, already using the canonical `SOURCES_AND_CAPABILITIES.md` vocabulary (`BLOCKERS.md` B6 partially addressed) — but route hints are informational only so far, nothing routes on them yet |
| 10 | Model Routing | **Single-provider baseline done** (Milestone 1); routing between multiple providers not started | `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md`; `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` | `controlplane/models/registry.py` currently returns the one configured Groq provider. Model pool (Qwen3 ~1.3B / 4B / Grok) from `DECISIONS.md` not yet implemented — Groq was used instead as the first real, available provider to prove the runtime backbone |
| 11 | RAG | Not started (encoder ready) | `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` §3-9 | The local embedding model (`controlplane/models/local_hf_provider.py`) was deliberately selected in Milestone 2 to double as the retrieval encoder — no second embedding model download needed |
| 12 | RAG Adequacy | Not started | `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` §10-15 | Output enum: `SUFFICIENT/PARTIALLY_SUFFICIENT/INSUFFICIENT/CONFLICTING` |
| 13 | Baseline Evaluation | Not started | `docs/specs/FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md` | **Blocked by `BLOCKERS.md` B5** — no real human-labeled responses exist to evaluate against yet. `model_invocations` now records real telemetry this layer can consume once it exists |
| 14 | Risk × Confidence Decision Engine | Not started | `docs/architecture/RUNTIME_FLOW.md` §19; `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §43, §64.2 | Use the canonical decision enum from `DECISIONS.md` |
| 15 | Intervention Engine | Not started | `docs/specs/INTERVENTION_ENGINE_IMPLEMENTATION_SPEC.md`; `docs/architecture/FAILURE_AND_RECOVERY.md` §7 | Use the canonical 16-value intervention vocabulary from `DECISIONS.md`. `execution_ledger`'s `INTERVENTION` action_type is already documented and ready to use |
| 16 | Replanning | Not started | `docs/architecture/FAILURE_AND_RECOVERY.md` §8; `docs/architecture/RUNTIME_FLOW.md` §22 | |
| 17 | Verification + Trust | Not started | `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §38-42 | Trust levels: `HIGH/MEDIUM/LOW`, not a raw score |
| 18 | Agent / Tool Control | Not started | `PRODUCT_THESIS_UPDATED.md` §14; `docs/architecture/AGENTS_RESEARCH_ALIGNED_UPDATED.md` §19 | |
| 19 | Trajectory Governance | Not started | `docs/architecture/AGENTS_RESEARCH_ALIGNED_UPDATED.md` §75.3, §75.8-75.10 | Behavioral drift, permission lineage, action state |
| 20 | Shadow Mode | Not started | `docs/architecture/RUNTIME_FLOW.md` §34 | |
| 21 | Dashboard | Not started | `PRODUCT_THESIS_UPDATED.md` §24 | Now has real trajectory/ledger/event data to visualize instead of only a design |
| 22 | Scale / Reliability | Not started | `docs/architecture/SCALE_ARCHITECTURE_UPDATED.md` | Load testing against the ~10,000/week assumption; write `NOT MEASURED` until actually measured |
| 23 | Data-Driven Learning | Not started | `PRODUCT_THESIS_UPDATED.md` §26-28 | Only after enough real (non-synthetic) execution data exists |

## Deferred / Out of Scope for Now

- Real human annotation of the 270 annotation cases (`docs/DATA/DATASET_GAPS.md`).
- Real LLM response generation against the query-profile dataset (the *mechanism* now exists — `model_invocations` — but nothing has run the actual 270-record dataset through it yet).
- External dataset integration ("Person A" track — `docs/DATA/DATASET_REGISTRY.md`'s external-candidates table is still empty).
- Reconciling every remaining terminology variant across `docs/architecture/` and `docs/specs/` beyond what `CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §64 already covers (`BLOCKERS.md` B3).
- Fine-tuning any component (explicitly deferred by every relevant doc until a baseline shows a measured, specific weakness).
- Transcribing the remaining pages of the original competition brief (`BLOCKERS.md` B7).
- Model routing across multiple providers (Layer 10's full scope — currently one fixed Groq model).
- Redis Streams-backed event transport (currently in-process; `EventTransport` interface is ready for the swap).
- Live Groq-vs-local classification comparison (harness built and run once; remote side `NOT_MEASURED` — needs a `GROQ_API_KEY` supplied in-session to actually execute).
- Reworking Query Profiler complexity classification (near chance-level for both baselines — see `docs/EVALUATION/QUERY_PROFILER_RESULTS.md`).
- Reworking Risk Profiler's decision-support/governance blind spot (missed its one true HIGH_RISK example — see `docs/EVALUATION/RISK_PROFILER_RESULTS.md`).
- Re-downloading the local embedding model with `allow_patterns` restricted to the PyTorch/safetensors files only (the current cache includes unused ONNX/OpenVINO/TF variants from `snapshot_download`'s default behavior — a minor disk-space inefficiency, not a functional issue).

## Next Action

Awaiting explicit instruction before continuing. Candidates: Execution Graph (Layer 4), Data/Capability Routing (Layer 9, inputs now ready), or extending model routing across multiple providers (rest of Layer 10) — see `docs/PROJECT_STATE/BLOCKERS.md` for what each would need resolved first.
