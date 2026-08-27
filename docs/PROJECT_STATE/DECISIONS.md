# ControlPlane.ai — Decisions Log

Each entry: the decision, where it's defined, and its status. This log records decisions already made in the architecture/data docs (so Layer 1+ implementation doesn't have to re-derive them) plus decisions made during the Layer 0 audit itself. It does not re-litigate them — see `BLOCKERS.md` for anything still open.

## Standing Architecture Decisions (from existing docs — not new)

| Decision | Defined in | Status |
|---|---|---|
| Storage stack: PostgreSQL (system of record) + Qdrant (vector retrieval) + Redis (cache/streams/coordination); no Chroma, Pinecone, Kafka, or Kubernetes in the prototype | `docs/DATA/DATA_STORAGE_ARCHITECTURE.md`, `docs/DATA/QDRANT_REDIS_DATA_CONTRACT.md` | Locked for prototype |
| API framework: FastAPI, small stateless worker pool, Dockerized | `docs/architecture/SCALE_ARCHITECTURE_UPDATED.md` §"Prototype stack" | Recommended, not yet built |
| Answer-model pool: Qwen3 ~1.3B (very-small/fast), Qwen3 4B (medium), Grok API (strong reasoning escalation); Qwen3 8B explicitly excluded | `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md` | Current decision |
| Judge model: Prometheus 2 (7B-class), few-shot first, fine-tune only after evidence of systematic weakness | `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md` | Current decision — note `docs/specs/FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md` §46 separately lists "final LLM judge" as *undecided*; read the "MODEL_AND_EVALUATION_DECISIONS.md" choice as the current default, not yet declared final |
| No fine-tuning of any component at V0 (`LOCAL ML MODELS REQUIRED = 0`) | `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §6, §55 | Locked for prototype |
| MCP capability groups at launch: Model, SQL/Data, RAG/Retrieval, Web/External Data, Agent/Tools (5 groups) | `PRODUCT_THESIS_UPDATED.md` §11.1, `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §45 | Locked for prototype |
| MCP is a capability/interoperability fabric; ControlPlane (not MCP) owns all decisions | Stated identically across nearly every architecture doc | Non-negotiable per `AGENTS_RESEARCH_ALIGNED_UPDATED.md` |
| Workload assumption: ~10,000 interactions/week (an operationalization of the brief's "tens of thousands," treated as a planning assumption, not a hard target) | `docs/architecture/SCALE_ARCHITECTURE_UPDATED.md`, `PRODUCT_THESIS_UPDATED.md` §2 | Planning assumption |
| Data quality: every record must carry a `provenance` field (`HUMAN`/`EXPERT`/`LLM_JUDGE`/`AUTOMATIC`/`SYNTHETIC`/`DERIVED`); LLM-generated labels never silently treated as ground truth | `docs/DATA/DATA_QUALITY.md`, `docs/DATA/ANNOTATION_GUIDELINES.md` | Locked, enforced in all generated data |

## Decisions Made During This Audit (2026-08-27)

| Decision | Reason | Where recorded |
|---|---|---|
| Canonical 16-value intervention vocabulary is the `ANNOTATION_GUIDELINES.md` list (`KEEP...BLOCK` + `ABORT` for system records, `OTHER` for human-annotation records) | This vocabulary was the most consistently repeated across 5+ independent docs; other variants (Model Router actions, Cascade Controller outputs, Event Model's illustrative payload examples) are adjacent, narrower vocabularies, not competitors | `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §64.1 |
| Canonical top-level decision outcome is `PASS, MONITOR, INTERVENE, ESCALATE, ABSTAIN, BLOCK, REPLAN, HUMAN_REVIEW` (the `POSTGRES_SCHEMA.md` `decisions.decision` enum) | Already the persisted-schema value; narrower local vocabularies (tool-authorization `ALLOW/MODIFY/HUMAN/BLOCK`, cascade `STOP/CONTINUE`) feed into this, they don't replace it | §64.2, same file |
| Canonical severity scale is `S0_INFO...S4_CRITICAL` (`FAILURE_AND_RECOVERY.md`), not `EVENT_MODEL.md`'s `info/notice/warning/high/critical` | `FAILURE_AND_RECOVERY.md` is ahead of `EVENT_MODEL.md` in the master spec's own §0 source-of-truth order; the event-envelope field is redefined as a narrower transport-level signal with a documented (non-strict) mapping to the governance scale | §64.3, same file |
| `init_postgres_schema.sql`'s `enterprise_demo` schema (NexaConsult Global) is documented as authoritative in `POSTGRES_SCHEMA.md` §12–14; the CSV dataset in `data/synthetic_enterprise/database/` is documented as a separate, unreconciled artifact rather than silently merged with it | The SQL is real, executable ground truth and explicitly claims to implement `POSTGRES_SCHEMA.md`; the CSVs have an incompatible (SaaS-shaped) schema with no stated relationship to either | `docs/DATA/POSTGRES_SCHEMA.md` §12 |
| `docs/PROJECT_STATE/` created (did not exist) with the five files this bootstrap's §12 requires | Explicit instruction; no prior art to preserve | This folder |

## Decisions Made During Layer 1 (2026-08-27)

| Decision | Reason | Where recorded |
|---|---|---|
| Concrete stack adopted: Python 3.11, FastAPI, Pydantic v2, `pyproject.toml` (setuptools backend), `uvicorn` as the ASGI server, `pytest`+`httpx` for tests | Promotes `SCALE_ARCHITECTURE_UPDATED.md`'s "recommended" prototype stack to an actual, adopted decision — the only concrete stack recommendation anywhere in the docs | `pyproject.toml`; this entry |
| Structured logging built on stdlib `logging` + `contextvars`, not a third-party library (e.g. `structlog`) | Layer 1 has no need for anything beyond JSON-formatted records carrying `request_id`/`trace_id`/`trajectory_id`/`timestamp`/`component`/`severity`/`message`; contextvars make IDs available to every logger automatically without passing them through every call, and a stdlib-only solution keeps Layer 1's dependency footprint minimal (Rule 4) | `controlplane/logging_config.py` |
| Identifier format: `req_<uuid4>`, `trace_<uuid4>`, `traj_<uuid4>` | Human-scannable in logs (which ID is which at a glance) while remaining globally unique; no doc mandates a specific format, so this is a new, first, decision | `controlplane/context.py` |
| `ExecutionState` fields limited to exactly the bootstrap's Layer 1 minimum (`request_id, trace_id, trajectory_id, query, current_status, current_step, plan_id, plan_version, created_at, updated_at, errors, metadata`), with `metadata` as the sole extension point | Explicit instruction: "Do not invent unnecessary fields." `RUNTIME_FLOW.md`'s much larger `ExecutionState` (query_profile, risk_state, evidence, models_used, ...) belongs to later layers that don't exist yet | `controlplane/state.py` |
| `current_status` is a 4-value enum (`RECEIVED, PROCESSING, COMPLETED, FAILED`), not the larger status vocabularies defined in `CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md` §6 or `ControlPlane_High_Level_Architecture_OPTIMAL.md`'s Abstention statuses | Those larger vocabularies describe outcomes (escalation, abstention, human review, partial completion) that don't exist until later layers; adopting them now would be unimplemented surface area | `controlplane/state.py` |
| Error contract limited to 5 classes (`VALIDATION_ERROR, CONFIGURATION_ERROR, INTERNAL_ERROR, DEPENDENCY_ERROR, TIMEOUT_ERROR`) rather than the full `CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md` §7 taxonomy (`MODEL_ERROR, RETRIEVAL_ERROR, ...`) | Only these 5 can actually occur before any capability exists; later layers add their own error classes to `controlplane/errors.py` as those capabilities are built, rather than pre-declaring unused error codes | `controlplane/errors.py` |
| `ResponseEnvelope` carries no trust/risk/confidence/evaluation fields | Explicit instruction: do not fake outputs from subsystems that don't exist yet | `controlplane/schemas.py` |

Anything not listed above and not resolved by an existing doc is open — see `BLOCKERS.md`. Do not treat silence as a decision.
