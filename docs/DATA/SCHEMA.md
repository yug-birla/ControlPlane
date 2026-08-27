# ControlPlane Query Profile Schema

## Purpose

This document defines the schema for the ControlPlane query dataset.

Each query record contains the query-profile fields specified in the project data plan. The schema was frozen at v0.1 (see `docs/DATA/DATA_CHANGELOG.md`) and is implemented authoritatively in `data/schemas/query_profile.schema.json`. This document is the human-readable description of that JSON Schema; if the two ever disagree, the JSON Schema file is authoritative.

## Query Profile Fields

Each query profile contains the following fields:

| Field | Type | Description | Allowed values |
|---|---|---|---|
| `query_id` | string | Unique identifier for the query profile. | e.g. `QP-001` |
| `query` | string | The query being evaluated. | free text |
| `intent` | string | The intent represented by the query. | free text |
| `domain` | string | The domain associated with the query. | free text |
| `knowledge_type` | string | The type of knowledge required by the query. | free text |
| `required_data_sources` | array&lt;string&gt; | Data sources required to address the query. | see `SOURCES_AND_CAPABILITIES.md` |
| `required_capabilities` | array&lt;string&gt; | Capabilities required to address the query. | see `SOURCES_AND_CAPABILITIES.md` |
| `complexity` | string | Complexity level associated with the query. | `low`, `medium`, `high` |
| `risk` | string | Risk associated with the query. | `NO_ACTION`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`, `CRITICAL` |
| `actionability` | string | Actionability associated with the query. | free text (not yet enumerated — see Currently Unspecified) |
| `sensitivity` | string | Sensitivity associated with the query. | `NONE`, `POTENTIAL_PII`, `PII_EXPOSURE`, `SENSITIVE_DATA_EXPOSURE` |
| `ambiguity` | string | Ambiguity associated with the query. | `low`, `medium`, `high` |
| `expected_route` | string | Expected route for handling the query. | free text (not yet enumerated — see Currently Unspecified) |
| `taxonomy_labels` | array&lt;string&gt; | Taxonomy label(s) assigned to the query. Not mutually exclusive. | see Initial Taxonomy below |
| `provenance` | string | Where this record (and its labels) came from. | `HUMAN`, `EXPERT`, `LLM_JUDGE`, `AUTOMATIC`, `SYNTHETIC`, `DERIVED` |

Optional fields present in the JSON Schema but not required on every record: `source_dataset`, `source_license`, `failure_mode`, `generation_date`, `prompt_version`, `validation_method`.

`risk` reuses the same five-value scale as the Annotation Guidelines' `action_risk` label (see `ANNOTATION_GUIDELINES.md`); `sensitivity` reuses the same four-value scale as the Annotation Guidelines' `privacy` label. They are recorded as separate fields because one is assessed at query-profiling time and the other during response annotation.

## Required Field List

The query profile requires the following fields (see `data/schemas/query_profile.schema.json` `required`):

1. `query_id`
2. `query`
3. `intent`
4. `domain`
5. `knowledge_type`
6. `required_data_sources`
7. `required_capabilities`
8. `complexity`
9. `risk`
10. `actionability`
11. `sensitivity`
12. `ambiguity`
13. `expected_route`
14. `taxonomy_labels`
15. `provenance`

## Taxonomy Relationship

The query dataset uses the initial taxonomy defined below, carried on each record via the `taxonomy_labels` field.

Queries may have multiple labels.

## Initial Taxonomy

The initial taxonomy consists of the following labels:

- `PUBLIC_FACTUAL`
- `PRIVATE_FACTUAL`
- `RAG`
- `INSUFFICIENT_RAG`
- `SQL`
- `ANALYTICAL`
- `REASONING`
- `CODING`
- `RECOMMENDATION`
- `DECISION_SUPPORT`
- `MEMORY`
- `CHAT_HISTORY`
- `AGENTIC`
- `HIGH_RISK_AGENTIC`
- `SENSITIVE`
- `AMBIGUOUS`
- `MULTI_SOURCE`
- `MULTI_STEP`

These taxonomy labels are not mutually exclusive. A single query may be assigned multiple labels.

## Currently Unspecified

`actionability` and `expected_route` are typed as free-text strings in the frozen v0.1 schema; no closed allowed-value set has been ratified for either field yet (the generated datasets use ad hoc values — see `DATASET_GAPS.md`). `required_data_sources` and `required_capabilities` are also free-text arrays: the canonical, closed vocabularies for these live in `SOURCES_AND_CAPABILITIES.md`, but the generated datasets currently use a broader, more granular set of values that has not yet been reconciled against that canonical vocabulary. This reconciliation is a known open item — see `DATASET_GAPS.md`.

These details should not be invented; they require clarification or later specification before being treated as closed enums.

## Version

v0.1 — Frozen 2026-08-26 per `DATA_CHANGELOG.md`. Large-scale generation against this schema is complete (see `DATASET_REGISTRY.md`).
