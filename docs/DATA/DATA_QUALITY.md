# ControlPlane Data Quality Policy

## Purpose

This document defines the data quality rules for the ControlPlane dataset.

## Rejection / Quarantine Criteria

Reject or quarantine any record that has:

- missing required schema fields
- broken encoding
- duplicate query_id
- contradictory labels (e.g. risk=NO_ACTION but taxonomy=HIGH_RISK_AGENTIC)
- unclear or missing annotation
- missing provenance
- unknown license for external data
- unauthorized personal data
- benchmark leakage
- test/challenge examples accidentally used for tuning

## Deduplication

At minimum deduplicate using:

1. exact hash of the `query` field
2. normalized-text hash (lowercase, punctuation stripped)

For large collections, investigate semantic duplicates.

## Balance Targets

| Difficulty | Target |
|---|---:|
| Easy / low risk | 20% |
| Normal | 30% |
| Complex | 20% |
| Failure-triggering | 20% |
| High-risk / adversarial | 10% |

## Provenance Requirement

Every record must carry a `provenance` field from:
- HUMAN
- EXPERT
- LLM_JUDGE
- AUTOMATIC
- SYNTHETIC
- DERIVED

LLM-generated labels must not silently be treated as ground truth.

## Version

v0.1 — Initial data quality policy.
