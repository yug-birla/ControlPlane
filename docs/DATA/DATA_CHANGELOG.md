# ControlPlane Data Changelog

## [0.4] - 2026-08-27

### Corrections (accuracy)
- `query_profiles_large.json` and `annotation_cases.json` record counts corrected from 250 to their actual count, 270, in `DATASET_REGISTRY.md` and `README.md`.
- `annotation_cases.json` status corrected from "structure only / labels PENDING" to "fully populated with synthetic placeholder labels; human/expert labels PENDING" — the file already contains complete `SYNTHETIC`-provenance labels, not just structure.
- `nexaconsult_evaluation_queries.json` / `controlplane_evaluation_queries.json` counts corrected from "~100" to the exact count, 100.
- `POSTGRES_SCHEMA.md` §12–14 (Synthetic Enterprise Domain) rewritten to match the tables actually created by `init_postgres_schema.sql` (the NexaConsult Global consulting-company schema), which differ from the generic customers/products/orders tables previously documented there. Added an explicit note that `data/synthetic_enterprise/database/*.csv` is a separate, unreconciled dataset with a different (SaaS) shape.
- `DATA_STORAGE_ARCHITECTURE.md` §5's `enterprise_demo` table list updated to match.

### Completeness
- `SCHEMA.md` rewritten: fixed pervasive literal backslash-escaping that broke every heading/field/list item; added the `taxonomy_labels` and `provenance` fields (present in the frozen JSON Schema but missing from this document); added known enum values for `complexity`, `risk`, `sensitivity`, `ambiguity`.
- `POSTGRES_SCHEMA.md` §15 (Evaluation Database) completed with the `responses`, `judgments`, `intervention_labels`, `trajectory_labels`, and evaluation-scoped `query_profiles` tables that `DATA_STORAGE_ARCHITECTURE.md` already listed but that were never defined; added `experiment_runs` (§16.2) distinct from `benchmark_runs`.
- `DATA_GENERATION.md` completed (previously ended mid-sentence with an unclosed code fence and stopped short of its own stated purpose).

### Consistency
- Intervention taxonomy unified to the 16-value `ANNOTATION_GUIDELINES.md` vocabulary (adding `OTHER`/`ABORT` where each was missing) across `CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md` §14, `POSTGRES_SCHEMA.md` §6.3, `PRODUCT_THESIS_UPDATED.md` §18, and `README.md`.
- Stripped ~157 leftover AI-citation artifacts (`fileciteturn...` tokens, invisible private-use-area characters) from `POSTGRES_SCHEMA.md`, `QDRANT_REDIS_DATA_CONTRACT.md`, `DATA_STORAGE_ARCHITECTURE.md`, and several `docs/architecture` and `docs/specs` files.
- Added `docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md` §64 "Terminology Alignment," declaring canonical spellings for the intervention vocabulary, top-level decision outcomes, severity scale, and model identifiers that had multiple non-identical versions across the architecture/specs doc set.
- Flagged (not silently resolved) the mismatch between `SOURCES_AND_CAPABILITIES.md`'s canonical `required_data_sources`/`required_capabilities` values and the more granular values actually used in generated data — see `DATASET_GAPS.md`.

## [0.3] - 2026-08-27

### Documentation Reorganization

All root-level MD files moved into structured `docs/` subdirectories. Root now contains only `PRODUCT_THESIS_UPDATED.md` and `README.md`.

#### Moved → `docs/architecture/` (10 files)
`AGENTS_RESEARCH_ALIGNED_UPDATED.md`, `ControlPlane_High_Level_Architecture_OPTIMAL.md`, `CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md`, `CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md`, `SCALE_ARCHITECTURE_UPDATED.md`, `RUNTIME_FLOW.md`, `EVENT_MODEL.md`, `FAILURE_AND_RECOVERY.md`, `TRAJECTORY_AND_LEDGER.md`, `MODEL_AND_EVALUATION_DECISIONS.md`

#### Moved → `docs/specs/` (4 files)
`CONTROLPLANE_ROUTING_SYSTEM_SPEC.md`, `CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md`, `INTERVENTION_ENGINE_IMPLEMENTATION_SPEC.md`, `FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md`

#### Moved → `docs/DATA/` (3 files — data infrastructure)
`DATA_STORAGE_ARCHITECTURE.md`, `POSTGRES_SCHEMA.md`, `QDRANT_REDIS_DATA_CONTRACT.md`

#### Created
- `README.md` — root navigation guide covering all directories, files, schemas, and project status

---

## [0.2] - 2026-08-27

### Repository Cleanup and Reorganization

#### Deleted (Corrupt Data)
- `smriti-data/queries.json` — 250 records, all containing identical query "What is the capital of France?", all with `domain: "P"` (invalid). Not recoverable; violates schema.
- `smriti-data/annotations.json` — 250 records, all with `case_id: "CP_Q0001"` (same ID repeated). Not recoverable; violates schema.

#### Deleted (Exact Duplicates of Root/docs Files)
From `smriti-data/` root: `AGENTS_RESEARCH_ALIGNED_UPDATED.md`, `ControlPlane_High_Level_Architecture_OPTIMAL.md`, `EVENT_MODEL.md`, `FAILURE_AND_RECOVERY.md`, `PRODUCT_THESIS_UPDATED.md`, `RUNTIME_FLOW.md`, `SCALE_ARCHITECTURE_UPDATED.md`, `TRAJECTORY_AND_LEDGER.md`, `ANNOTATION_GUIDELINES.md`, `SCHEMA.md`, `DATA_GENERATION.md`

From `smriti-data/DATA_STRUCTURE/`: `DATA_STORAGE_ARCHITECTURE.md`, `POSTGRES_SCHEMA.md`, `QDRANT_REDIS_DATA_CONTRACT.md` (identical to root-level files)

#### Moved (Unique Files — Correctly Placed)
- `smriti-data/NEXACONSULT_EVALUATION_QUERIES.json` → `data/evaluation/nexaconsult_evaluation_queries.json`
- `smriti-data/CONTROLPLANE_EVALUATION_QUERIES.json` → `data/evaluation/controlplane_evaluation_queries.json`
- `smriti-data/CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md` → `docs/DATA/CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md`
- `smriti-data/SOURCES_AND_CAPABILITIES.md` → `docs/DATA/SOURCES_AND_CAPABILITIES.md`
- `smriti-data/enterprise_nexaconsult.sql` → `data/synthetic_enterprise/nexaconsult_enterprise.sql`
- `smriti-data/init_postgres_schema.sql` → `data/synthetic_enterprise/init_postgres_schema.sql`

#### Directory Removed
- `smriti-data/` — Entire directory removed after all unique content migrated

### Schema Status
- Query Profile schema v0.1 unchanged. See `data/schemas/query_profile.schema.json`.
- Evaluation query format (Person A's work) is a distinct dataset type — not unified with query profiles.

## [0.1] - 2026-08-26

### Created
- `docs/DATA/SCHEMA.md` — Query profile schema and taxonomy
- `docs/DATA/ANNOTATION_GUIDELINES.md` — Annotation vocabulary v0.1
- `docs/DATA/DATA_GENERATION.md` — Generation methodology
- `docs/DATA/DATA_STRATEGY.md` — Overall data strategy
- `docs/DATA/DATASET_REGISTRY.md` — Dataset registry
- `docs/DATA/EVALUATION_PROTOCOL.md` — Evaluation protocol
- `docs/DATA/DATA_QUALITY.md` — Quality policy
- `docs/DATA/DATASET_GAPS.md` — Gap analysis
- `docs/DATA/DATA_CHANGELOG.md` — This file
- `docs/DATA/QUERY_PROFILES.json` — 30 representative query profiles

### Schema Status
- Schema v0.1 frozen. Large-scale generation authorized.

### Completed Datasets
- 30 representative query profiles (Task 6 requirement)
- 250 large query profile dataset
- 150 RAG cases
- 150 intervention cases
- 75 counterfactual cases
- 75 agent trajectories
- Annotation case structure (250 cases, labels PENDING)
- Synthetic enterprise environment (8 DB tables, 30 documents, 75 chat records)
- Evaluation splits (train/validation/test/challenge)

### Pending
- Actual model responses
- Human annotation labels
- LLM-judge labels
- Experimental results
- External dataset integration (Person A)
