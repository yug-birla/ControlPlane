# ControlPlane

> **Adaptive control plane for AI execution** — dynamic routing, evaluation, intervention, and self-healing for AI workflows.

The primary source of truth for the project vision is [`PRODUCT_THESIS_UPDATED.md`](PRODUCT_THESIS_UPDATED.md).

---

## Repository Structure

```
ControlPlane/
│
├── PRODUCT_THESIS_UPDATED.md          ← START HERE — core vision and design principles
│
├── docs/
│   ├── architecture/                  ← System design, runtime flow, event model
│   ├── specs/                         ← Component implementation specifications
│   └── DATA/                          ← Data strategy, schemas, annotation guidelines
│
└── data/
    ├── raw/generated/                 ← Bulk generated datasets
    ├── annotations/                   ← Annotation cases (pending human labels)
    ├── evaluation/                    ← Evaluation splits + intervention query sets
    ├── synthetic_enterprise/          ← Enterprise simulation environment (DB, docs, chat, SQL)
    ├── schemas/                       ← JSON schema definitions
    ├── scripts/                       ← Data generation and validation scripts
    └── reports/                       ← Dataset quality scorecards
```

---

## `docs/architecture/` — System Architecture

Core system design documents covering how the ControlPlane works end-to-end.

| File | Description |
|---|---|
| [`PRODUCT_THESIS_UPDATED.md`](PRODUCT_THESIS_UPDATED.md) | Vision, lifecycle (Understand → Plan → Execute → Observe → Replan → Verify → Respond → Learn), query fingerprint design |
| [`ControlPlane_High_Level_Architecture_OPTIMAL.md`](docs/architecture/ControlPlane_High_Level_Architecture_OPTIMAL.md) | High-level system architecture overview |
| [`CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md`](docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md) | Master implementation specification |
| [`CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md`](docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md) | Cross-cutting concerns: auth, logging, observability |
| [`RUNTIME_FLOW.md`](docs/architecture/RUNTIME_FLOW.md) | Request lifecycle and execution flow |
| [`EVENT_MODEL.md`](docs/architecture/EVENT_MODEL.md) | Event types, event bus design, event sourcing |
| [`FAILURE_AND_RECOVERY.md`](docs/architecture/FAILURE_AND_RECOVERY.md) | Failure detection, recovery strategies, circuit breakers |
| [`TRAJECTORY_AND_LEDGER.md`](docs/architecture/TRAJECTORY_AND_LEDGER.md) | Agent trajectory tracking, append-only execution ledger |
| [`SCALE_ARCHITECTURE_UPDATED.md`](docs/architecture/SCALE_ARCHITECTURE_UPDATED.md) | Horizontal scaling, load balancing, distributed execution |
| [`MODEL_AND_EVALUATION_DECISIONS.md`](docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md) | Model selection rationale and evaluation decision log |
| [`AGENTS_RESEARCH_ALIGNED_UPDATED.md`](docs/architecture/AGENTS_RESEARCH_ALIGNED_UPDATED.md) | Research alignment — agents, tool use, agentic patterns |

---

## `docs/specs/` — Component Specifications

Detailed implementation specs for individual ControlPlane subsystems.

| File | Description |
|---|---|
| [`CONTROLPLANE_ROUTING_SYSTEM_SPEC.md`](docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md) | Query routing logic, route selection, capability matching |
| [`CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md`](docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md) | RAG pipeline, retrieval sufficiency, hallucination detection |
| [`INTERVENTION_ENGINE_IMPLEMENTATION_SPEC.md`](docs/specs/INTERVENTION_ENGINE_IMPLEMENTATION_SPEC.md) | Intervention decision engine — KEEP, BLOCK, REDACT, VERIFY, etc. |
| [`FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md`](docs/specs/FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md) | Evaluation governance, scoring, benchmark execution |

---

## `docs/DATA/` — Data Strategy & Schema

Everything related to the dataset workstream.

| File | Description |
|---|---|
| [`SCHEMA.md`](docs/DATA/SCHEMA.md) | Query profile schema — canonical field definitions and taxonomy |
| [`SOURCES_AND_CAPABILITIES.md`](docs/DATA/SOURCES_AND_CAPABILITIES.md) | Allowed values for `required_data_sources` and `required_capabilities` |
| [`ANNOTATION_GUIDELINES.md`](docs/DATA/ANNOTATION_GUIDELINES.md) | Annotation vocabulary: correctness, grounding, safety, privacy, intervention |
| [`DATA_STRATEGY.md`](docs/DATA/DATA_STRATEGY.md) | Overall data strategy and 9-layer data model |
| [`DATA_GENERATION.md`](docs/DATA/DATA_GENERATION.md) | Generation methodology and sequencing rules |
| [`CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md`](docs/DATA/CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md) | Person A / Person B task split and work instructions |
| [`DATASET_REGISTRY.md`](docs/DATA/DATASET_REGISTRY.md) | Catalog of all datasets with file paths, record counts, status |
| [`DATA_CHANGELOG.md`](docs/DATA/DATA_CHANGELOG.md) | History of all schema and dataset changes |
| [`EVALUATION_PROTOCOL.md`](docs/DATA/EVALUATION_PROTOCOL.md) | Evaluation protocol and benchmark methodology |
| [`DATA_QUALITY.md`](docs/DATA/DATA_QUALITY.md) | Quality policy and validation rules |
| [`DATASET_GAPS.md`](docs/DATA/DATASET_GAPS.md) | Gap analysis — what is missing from each data layer |
| [`DATA_STORAGE_ARCHITECTURE.md`](docs/DATA/DATA_STORAGE_ARCHITECTURE.md) | Storage architecture: Postgres, Qdrant, Redis |
| [`POSTGRES_SCHEMA.md`](docs/DATA/POSTGRES_SCHEMA.md) | Full Postgres table and schema definitions |
| [`QDRANT_REDIS_DATA_CONTRACT.md`](docs/DATA/QDRANT_REDIS_DATA_CONTRACT.md) | Qdrant vector store and Redis data contracts |
| [`QUERY_PROFILES.json`](docs/DATA/QUERY_PROFILES.json) | 30 representative query profiles (schema reference examples) |

---

## `data/` — Datasets

### `data/raw/generated/` — Bulk Generated Datasets
| File | Records | Description |
|---|---|---|
| `query_profiles_large.json` | 250 | Full query profile dataset covering all taxonomy categories |
| `rag_cases.json` | 150 | RAG retrieval cases with sufficiency labels |
| `intervention_cases.json` | 150 | Intervention decision cases with expected outcomes |
| `counterfactual_cases.json` | 75 | Counterfactual route and model swap cases |
| `agent_trajectories.json` | 75 | Multi-step agentic execution trajectories |

### `data/annotations/`
| File | Records | Description |
|---|---|---|
| `annotation_cases.json` | 250 | Annotation cases — structure complete, **human labels PENDING** |

### `data/evaluation/` — Evaluation Splits & Intervention Query Sets
| File | Records | Description |
|---|---|---|
| `train/query_profiles_train.json` | 135 | Training split |
| `validation/query_profiles_validation.json` | 28 | Validation split |
| `test/query_profiles_test.json` | 30 | Test split |
| `challenge/query_profiles_challenge.json` | 77 | Challenge (held-out) split |
| `nexaconsult_evaluation_queries.json` | ~100 | Intervention evaluation — NexaConsult enterprise context |
| `controlplane_evaluation_queries.json` | ~100 | Intervention evaluation — ControlPlane system governance |

### `data/synthetic_enterprise/` — Enterprise Simulation Environment
| Path | Contents |
|---|---|
| `database/` | 8 CSV tables: employees, customers, orders, products, transactions, departments, revenue, support tickets |
| `documents/` | 30 enterprise policy documents (HR, infosec, travel, procurement, legal, etc.) |
| `chat/` | 75 simulated chat history records |
| `nexaconsult_enterprise.sql` | Full NexaConsult enterprise SQL schema and seed data |
| `init_postgres_schema.sql` | ControlPlane Postgres schema initialisation script |

### `data/schemas/` — JSON Schema Definitions
Formal JSON Schema (draft-07) files for each dataset type:
`query_profile`, `annotation_case`, `rag_case`, `intervention_case`, `counterfactual_case`, `agent_trajectory`

### `data/scripts/`
| File | Description |
|---|---|
| `generate_all_datasets.py` | Master data generation script |
| `validate_datasets.py` | Schema validation runner |
| `fill_annotations.py` | Annotation case population helper |

---

## Dataset Schema — Quick Reference

### Query Profile (Type 1)
Used in `data/raw/generated/`, `docs/DATA/QUERY_PROFILES.json`, and evaluation splits.
```json
{
  "query_id": "QP-001",
  "query": "...",
  "intent": "...",
  "domain": "artificial_intelligence",
  "knowledge_type": "public_factual",
  "required_data_sources": ["public_knowledge"],
  "required_capabilities": ["factual_retrieval"],
  "complexity": "low | medium | high",
  "risk": "NO_ACTION | LOW_RISK | MEDIUM_RISK | HIGH_RISK | CRITICAL",
  "actionability": "informational | procedural | generative | decisional | agentic",
  "sensitivity": "NONE | POTENTIAL_PII | PII_EXPOSURE | SENSITIVE_DATA_EXPOSURE",
  "ambiguity": "low | medium | high",
  "expected_route": "...",
  "taxonomy_labels": ["PUBLIC_FACTUAL"],
  "provenance": "SYNTHETIC"
}
```

### Evaluation Query (Type 2)
Used in `data/evaluation/nexaconsult_evaluation_queries.json` and `controlplane_evaluation_queries.json`.
```json
{
  "query_id": "Q001",
  "query": "...",
  "domain": "SQL | CHAT_HISTORY | SENSITIVE | HIGH_RISK_AGENTIC | AMBIGUOUS | REASONING | RAG",
  "proposed_action": "SELECT ... | UPDATE ... | DELETE ...",
  "evaluation": {
    "correctness": "CORRECT | PARTIALLY_CORRECT | INCORRECT",
    "privacy": "NONE | POTENTIAL_PII | PII_EXPOSURE | SENSITIVE_DATA_EXPOSURE",
    "action_risk": "NO_ACTION | LOW_RISK | MEDIUM_RISK | HIGH_RISK | CRITICAL",
    "intervention": "KEEP | VERIFY | REDACT | BLOCK | HUMAN_REVIEW | ASK_CLARIFICATION | CHANGE_DATA_SOURCE",
    "why": "..."
  }
}
```

---

## Intervention Taxonomy

| Label | Meaning |
|---|---|
| `KEEP` | Response is correct and safe — pass through |
| `VERIFY` | Response needs verification before delivery |
| `RETRIEVE_MORE` | Insufficient evidence — retrieve additional context |
| `CHANGE_DATA_SOURCE` | Switch to a more appropriate source |
| `REDACT` | Strip PII or sensitive content before delivery |
| `BLOCK` | Do not execute or return — policy violation |
| `HUMAN_REVIEW` | Escalate to human for authorization |
| `ASK_CLARIFICATION` | Request is too ambiguous — ask the user |
| `REPLAN` | Agent must replan the workflow |

---

## Status

| Layer | Status |
|---|---|
| Schema v0.1 | ✅ Frozen |
| Query profiles (250) | ✅ Complete |
| RAG / Intervention / Trajectory datasets | ✅ Complete |
| Evaluation splits (train/val/test/challenge) | ✅ Complete |
| Evaluation query sets (NexaConsult + CP) | ✅ Complete |
| Synthetic enterprise environment | ✅ Complete |
| Model responses | ⏳ Pending |
| Human annotation labels | ⏳ Pending |
| External dataset integration (Person A) | ⏳ Pending |
