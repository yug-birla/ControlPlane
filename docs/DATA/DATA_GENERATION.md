# ControlPlane Data Generation Methodology

## Purpose

This document defines the methodology used to produce the custom ControlPlane dataset. It records what was actually done; see `DATA_STRATEGY.md` for the higher-level rationale and layer model, and `DATA_CHANGELOG.md` for the dated history of what was produced.

The methodology is model- and provider-agnostic: which LLM(s) were used to synthesize records is not asserted here, since the goal is decision coverage of the ControlPlane control loop, not reproducing a specific generation stack.

## Generation Sequence

Large-scale generation was not started until the schema had been reviewed and stabilized. The sequence that was followed:

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

Schema v0.1 was frozen 2026-08-26 (see `DATA_CHANGELOG.md`), after which large-scale generation was authorized and executed for all dataset types tracked in `DATASET_REGISTRY.md`.

## What Was Generated

Per-record schemas are defined in `data/schemas/*.schema.json` and summarized in `SCHEMA.md`, `ANNOTATION_GUIDELINES.md`, and `DATASET_REGISTRY.md`. Every generated record carries a `provenance` field (see `DATA_QUALITY.md`); generated datasets currently use `SYNTHETIC` or `DERIVED` provenance — none carry `HUMAN` or `EXPERT` provenance yet (see `DATASET_GAPS.md`).

Every generated record also carries `generation_date`, and most carry `prompt_version` and `validation_method`, so that generation runs remain reproducible and re-auditable per the provenance rules in `DATA_QUALITY.md`.

## Version

v0.2 — Updated 2026-08-27. Documents the generation sequence actually followed and its outcome, superseding the pre-generation planning note in v0.1.
