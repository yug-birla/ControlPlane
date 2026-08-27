# ControlPlane.ai — Future Work / Implementation Plan by Layer

Layer order and success conditions are fixed by the implementation bootstrap. This file tracks status and points each layer at the doc(s) that already define its contract, so implementation doesn't have to re-derive the design. **Do not skip layers or start Layer N+1 before Layer N's success condition is met and documented in `PROGRESS.md`.**

| Layer | Name | Status | Governing doc(s) | Notes |
|---|---|---|---|---|
| 0 | Repository / Project Audit | **Done** (2026-08-27) | This folder | See `CURRENT_STATE.md`, `BLOCKERS.md` |
| 1 | Foundation (API entrypoint, request/trace/trajectory IDs, execution state stub, config, logging, error model, health checks) | Not started | `docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md` §2 (identifiers), §7 (error model), §20-21 (health/startup); `docs/architecture/SCALE_ARCHITECTURE_UPDATED.md` (prototype stack) | Success: a request enters the system and gets a valid execution context |
| 2 | Execution State + Trajectory | Not started | `docs/architecture/TRAJECTORY_AND_LEDGER.md`; `docs/DATA/POSTGRES_SCHEMA.md` §3, §9-10 | Trajectory Store (reconstructable history) vs. Execution Ledger (append-only facts) — keep distinct per the contract |
| 3 | Event Model | Not started | `docs/architecture/EVENT_MODEL.md` | Start with the canonical event list in that doc's §14; see `BLOCKERS.md` B3 for naming caveats |
| 4 | Execution Graph | Not started | `docs/architecture/RUNTIME_FLOW.md` §11-12; `PRODUCT_THESIS_UPDATED.md` §8 | |
| 5 | Capability / MCP Fabric | Not started | `PRODUCT_THESIS_UPDATED.md` §11; `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §45 | 5 capability groups: Model, SQL/Data, RAG/Retrieval, Web/External Data, Agent/Tools |
| 6 | Synthetic Data Environment | Partially done (data generated, not loaded into a running DB) | `docs/DATA/DATASET_REGISTRY.md`, `docs/DATA/POSTGRES_SCHEMA.md` §12-14 | **Resolve `BLOCKERS.md` B4 first** (two incompatible enterprise datasets) |
| 7 | Baseline Query Intelligence | Not started | `docs/DATA/SCHEMA.md`; `PRODUCT_THESIS_UPDATED.md` §6 | Create `docs/ALGORITHMS/QUERY_PROFILER.md` alongside this layer (see `BLOCKERS.md` B8) |
| 8 | Baseline Risk / Policy | Not started | `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` (Risk Profiler, R0/R1/R2) | |
| 9 | Data / Capability Routing | Not started | `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` (Capability Router) | **Resolve `BLOCKERS.md` B6 first** (data-source/capability taxonomy mismatch) |
| 10 | Model Routing | Not started | `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md`; `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` (Model Router) | Model pool already decided — see `DECISIONS.md` |
| 11 | RAG | Not started | `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` §3-9 | |
| 12 | RAG Adequacy | Not started | `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` §10-15 | Output enum: `SUFFICIENT/PARTIALLY_SUFFICIENT/INSUFFICIENT/CONFLICTING` |
| 13 | Baseline Evaluation | Not started | `docs/specs/FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md` | **Blocked by `BLOCKERS.md` B5** — no real responses/labels exist to evaluate against yet |
| 14 | Risk × Confidence Decision Engine | Not started | `docs/architecture/RUNTIME_FLOW.md` §19; `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §43, §64.2 | Use the canonical decision enum from `DECISIONS.md` |
| 15 | Intervention Engine | Not started | `docs/specs/INTERVENTION_ENGINE_IMPLEMENTATION_SPEC.md`; `docs/architecture/FAILURE_AND_RECOVERY.md` §7 | Use the canonical 16-value intervention vocabulary from `DECISIONS.md` |
| 16 | Replanning | Not started | `docs/architecture/FAILURE_AND_RECOVERY.md` §8; `docs/architecture/RUNTIME_FLOW.md` §22 | |
| 17 | Verification + Trust | Not started | `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §38-42 | Trust levels: `HIGH/MEDIUM/LOW`, not a raw score |
| 18 | Agent / Tool Control | Not started | `PRODUCT_THESIS_UPDATED.md` §14; `docs/architecture/AGENTS_RESEARCH_ALIGNED_UPDATED.md` §19 | |
| 19 | Trajectory Governance | Not started | `docs/architecture/AGENTS_RESEARCH_ALIGNED_UPDATED.md` §75.3, §75.8-75.10 | Behavioral drift, permission lineage, action state |
| 20 | Shadow Mode | Not started | `docs/architecture/RUNTIME_FLOW.md` §34 | |
| 21 | Dashboard | Not started | `PRODUCT_THESIS_UPDATED.md` §24 (renumbered from §23 during the 2026-08-27 audit) | |
| 22 | Scale / Reliability | Not started | `docs/architecture/SCALE_ARCHITECTURE_UPDATED.md` | Load testing against the ~10,000/week assumption; write `NOT MEASURED` until actually measured |
| 23 | Data-Driven Learning | Not started | `PRODUCT_THESIS_UPDATED.md` §26-28 | Only after enough real (non-synthetic) execution data exists |

## Deferred / Out of Scope for Now

- Real human annotation of the 270 annotation cases (`docs/DATA/DATASET_GAPS.md`).
- Real LLM response generation against the query-profile dataset.
- External dataset integration ("Person A" track — `docs/DATA/DATASET_REGISTRY.md`'s external-candidates table is still empty).
- Reconciling every remaining terminology variant across `docs/architecture/` and `docs/specs/` beyond what `CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §64 already covers (`BLOCKERS.md` B3).
- Fine-tuning any component (explicitly deferred by every relevant doc until a baseline shows a measured, specific weakness).
- Transcribing the remaining pages of the original competition brief (`BLOCKERS.md` B7).

## Next Action

Awaiting explicit instruction to begin Layer 1, per the bootstrap's "do not proceed automatically" rule.
