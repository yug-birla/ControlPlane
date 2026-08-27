# ControlPlane Dataset Registry

## Purpose

This document tracks all datasets considered, evaluated, and integrated for the ControlPlane project.

## Status Legend

| Status | Meaning |
|---|---|
| CANDIDATE | Identified, not yet inspected |
| INSPECTED | Schema and samples reviewed |
| SELECTED | Chosen for integration |
| INTEGRATED | Transformed and loaded |
| REJECTED | Inspected and rejected |

## External Dataset Candidates

| Dataset Name | Domain / Task | Status | Relevance | Priority | Notes |
|---|---|---|---|---|---|
| TBD — Person A to populate | | | | | |

## Custom (Internal) Datasets

| Dataset | File Path | Records | Status | Last Updated |
|---|---|---|---|---|
| Representative Query Profiles | `docs/DATA/QUERY_PROFILES.json` | 30 | COMPLETE | 2026-08-26 |
| Large Query Profile Dataset | `data/raw/generated/query_profiles_large.json` | 250 | COMPLETE | 2026-08-26 |
| RAG Cases | `data/raw/generated/rag_cases.json` | 150 | COMPLETE | 2026-08-26 |
| Intervention Cases | `data/raw/generated/intervention_cases.json` | 150 | COMPLETE | 2026-08-26 |
| Counterfactual Cases | `data/raw/generated/counterfactual_cases.json` | 75 | COMPLETE | 2026-08-26 |
| Agent Trajectories | `data/raw/generated/agent_trajectories.json` | 75 | COMPLETE | 2026-08-26 |
| Annotation Cases | `data/annotations/annotation_cases.json` | 250 | STRUCTURE ONLY | PENDING human annotation |
| Synthetic Enterprise DB | `data/synthetic_enterprise/database/` | 8 tables | COMPLETE | 2026-08-26 |
| Synthetic Enterprise Docs | `data/synthetic_enterprise/documents/` | 30 docs | COMPLETE | 2026-08-26 |
| Synthetic Chat History | `data/synthetic_enterprise/chat/` | 75 records | COMPLETE | 2026-08-26 |
| NexaConsult Evaluation Queries | `data/evaluation/nexaconsult_evaluation_queries.json` | ~100 | COMPLETE | 2026-08-27 |
| ControlPlane Evaluation Queries | `data/evaluation/controlplane_evaluation_queries.json` | ~100 | COMPLETE | 2026-08-27 |
| NexaConsult SQL Environment | `data/synthetic_enterprise/nexaconsult_enterprise.sql` | N/A | COMPLETE | 2026-08-27 |
| ControlPlane Postgres Init | `data/synthetic_enterprise/init_postgres_schema.sql` | N/A | COMPLETE | 2026-08-27 |

## Evaluation Dataset Notes

The files in `data/evaluation/` represent a **separate dataset type** from query profiles:

- **Schema**: `{query_id, query, domain, proposed_action, evaluation: {correctness, privacy, action_risk, intervention, why}}`
- **Purpose**: Evaluate whether the ControlPlane correctly decides how to intervene when given a query and a proposed system action
- **NexaConsult dataset**: Covers `SQL`, `CHAT_HISTORY`, `SENSITIVE`, `HIGH_RISK_AGENTIC`, `AMBIGUOUS`, `REASONING`, `RAG` domains against the NexaConsult enterprise SQL environment
- **ControlPlane dataset**: Covers internal system governance queries against ControlPlane's own schema tables

## Gap Analysis

| ControlPlane Requirement | Covered By | Gap |
|---|---|---|
| Query profiling | Custom query profiles | None |
| Routing | Custom query profiles + counterfactuals | Needs model execution |
| Failure detection | Failure cases in intervention dataset | Needs model execution |
| RAG sufficiency | Custom RAG dataset | None |
| Intervention decisions | Custom intervention + evaluation query datasets | Needs human annotation |
| Agent safety | Custom trajectory dataset + evaluation queries | Needs human annotation |
| Cost / latency | Counterfactual dataset (structure) | Needs actual measurements |
| Human preference | Annotation cases | PENDING human annotation |
| Factuality | Annotation cases | PENDING model responses |

## Version

v0.2 — Updated 2026-08-27. Added NexaConsult and ControlPlane evaluation datasets and SQL environment files. Removed corrupt and duplicate data from `smriti-data/` directory (now deleted). All documentation consolidated to `docs/DATA/`.
