# ControlPlane Dataset Gaps

## Purpose

This document tracks known gaps in the ControlPlane dataset.

## Known Gaps

| Gap | Description | Resolution |
|---|---|---|
| Model responses | No actual LLM responses generated yet; `annotation_cases.json` model_response fields are placeholder text, not real model output | Requires model API execution |
| LLM-judge labels | No LLM-judge annotation yet | Requires judge execution |
| Human annotation | All 270 `annotation_cases.json` records carry `provenance: SYNTHETIC` placeholder labels; no `HUMAN` or `EXPERT` labels exist yet | Requires human annotators |
| Double annotation | The 20% `double_annotated` flag and `agreement_rate` in `annotation_cases.json` are synthetic placeholders, not real independent-annotator agreement | PENDING human workflow |
| Data-source / capability taxonomy reconciliation | `required_data_sources` and `required_capabilities` values used in generated query profiles are more granular than the canonical vocabulary in `SOURCES_AND_CAPABILITIES.md` and have not been mapped to it | PENDING reconciliation pass |
| Cost / latency measurements | No real measurements yet | Requires actual system execution |
| Route accuracy | Cannot measure without actual routing experiments | PENDING experiments |
| External dataset integration | Person A has not yet populated the registry | PENDING Person A |
| Baseline vs ControlPlane comparison | No experiments run yet | PENDING experiments |

## Notes

- Do not fabricate experimental results to fill these gaps.
- Mark all pending items clearly.
- Update this document as gaps are resolved.

## Version

v0.1 — Initial gap analysis.

v0.2 — 2026-08-27. Clarified that annotation-case labels exist but are synthetic placeholders, not human ground truth. Added the data-source/capability taxonomy reconciliation gap (see `SOURCES_AND_CAPABILITIES.md`).
