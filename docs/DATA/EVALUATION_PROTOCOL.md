# ControlPlane Evaluation Protocol

## Purpose

This document defines how ControlPlane is evaluated against the dataset.

## Evaluation Loop

Every evaluation case runs through:

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

## Metrics

### Query Intelligence
- intent accuracy
- data-source classification accuracy
- risk classification accuracy
- capability classification accuracy

### Routing
- route accuracy
- wrong-route rate
- unnecessary escalation rate

### Failure Detection
- failure precision
- failure recall
- false intervention rate
- missed failure rate

### Intervention
- intervention accuracy
- recovery success rate
- recovery failure rate

### Final Outcome
- correctness (per ANNOTATION_GUIDELINES.md)
- grounding (per ANNOTATION_GUIDELINES.md)
- factuality
- reasoning quality (per ANNOTATION_GUIDELINES.md)
- safety (per ANNOTATION_GUIDELINES.md)

### Efficiency
- latency (p50, p95)
- cost (tokens, model calls)
- tool calls per query
- model calls per query

## Comparison Experiment

Run the same query set through:

```text
BASELINE LLM   vs   CONTROLPLANE
```

Compare all metrics listed above.

> Do not populate comparison results until experiments are actually run. Mark as PENDING.

## Dataset Splits Used

| Split | Purpose |
|---|---|
| TRAIN | Development and tuning |
| VALIDATION | Intermediate evaluation during development |
| TEST | Final evaluation |
| CHALLENGE | Held-out difficult cases; not used for tuning |

## Challenge Set Rules

- Do not optimize directly against challenge examples.
- Challenge set is for final reporting only.
- Protect from leakage into training.

## Version

v0.1 — Initial evaluation protocol.
