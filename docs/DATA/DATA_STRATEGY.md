# ControlPlane Data Strategy

## Purpose

This document describes the overall data strategy for the ControlPlane project.

ControlPlane requires multi-layer evaluation data that supports the full control loop:

```text
UNDERSTAND → PLAN → EXECUTE → OBSERVE → EVALUATE
                    ↓
              FAILURE / SIGNAL
                    ↓
               INTERVENE
                    ↓
                REPLAN
                    ↓
                VERIFY
                    ↓
             FINAL ANSWER
```

A simple question-answer dataset is insufficient.

## Data Layers

| Layer | Description |
|---|---|
| Layer 1 — Query | Query profiles with intent, domain, taxonomy, route |
| Layer 2 — Response | Model outputs for query × capability variants |
| Layer 3 — Retrieval / Evidence | RAG cases, retrieved documents, sufficiency |
| Layer 4 — Execution / Route | Route selection, execution trace |
| Layer 5 — Failure | Failure type, signal, severity |
| Layer 6 — Intervention | Preferred intervention, reason, expected effect |
| Layer 7 — Agent Trajectory | Multi-step tool use, risk, intervention point |
| Layer 8 — Human Judgment | Correctness, grounding, safety, intervention label |
| Layer 9 — Outcome | Final answer quality, cost, latency |

## Team Responsibilities

- **Person A**: External dataset research, benchmark integration, dataset registry
- **Person B**: Custom dataset creation, annotation schema, query profiling, failure cases

## Anti-Duplication Rule

Person A identifies what external datasets already cover.
Person B fills the gaps with custom data.
Neither person silently redesigns the shared schema.

## Generation Sequence

```text
Schema
  ↓
Taxonomy
  ↓
30 representative examples
  ↓
Schema review
  ↓
Freeze v0.1
  ↓
Large-scale generation
```

Large-scale generation must not begin until the schema has been reviewed and stabilized.

## Data Quality Principles

- Optimize for ControlPlane decision coverage, not dataset size.
- Include failure-triggering cases, not only easy factual questions.
- Record provenance for all generated and external data.
- Protect the challenge set from routine tuning.

## Version

v0.1 — Initial strategy document.
