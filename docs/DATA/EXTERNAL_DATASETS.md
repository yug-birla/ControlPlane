# External (Public) Datasets

Per bootstrap section 12/13: "if a task lacks sufficient quality data, search public Hugging Face datasets... normalize into the project schema, track provenance." This file tracks every external dataset actually pulled into the project — none existed before Milestone 8; every prior milestone's data was either hand-authored (provenance `HUMAN`) or synthetically generated (provenance `SYNTHETIC`).

## `deepset/prompt-injections`

**Source:** https://huggingface.co/datasets/deepset/prompt-injections
**License:** Apache-2.0
**Version (pinned):** revision `4f61ecb038e9c3fb77e21034b22511b523772cdd`, verified via the live Hugging Face API on 2026-08-28 (not guessed from training-data memory).
**Schema (source):** two columns, `text` (str, the query) and `label` (int, 0=benign / 1=injection attempt).
**Label mapping:** `0 → NO_PATTERN_DETECTED`, `1 → INJECTION_PATTERN_DETECTED` (matching `controlplane.evaluation.evaluators.PromptInjectionEvaluator`'s own output vocabulary).
**Provenance:** `EXTERNAL` (a new provenance value added this milestone — the existing vocabulary, `HUMAN`/`EXPERT`/`LLM_JUDGE`/`AUTOMATIC`/`SYNTHETIC`/`DERIVED`, had no value for "real data from a public source, not authored by this project" — see `docs/PROJECT_STATE/DECISIONS.md`).
**Sample count:** 662 total (546 train + 116 test, the source dataset's own split; this project only evaluates against it, never trains on it as a supervised objective in the traditional sense, so the split matters here only for held-out k-NN reference-vs-test separation, not a train/val/test model-training pipeline).
**Splits:** `train` (546) and `test` (116), preserved from source, recorded per-record as a `split` field.
**Quality checks performed:** inspected the dataset card, license, and a real sample of rows (printed and read, not assumed) before adoption; confirmed label balance is reasonable (train: 343 benign / 203 injection; test: 56 benign / 60 injection) — no severe class imbalance requiring resampling.
**Limitations:** the source's injection examples lean toward a specific style (jailbreak-style role-play overrides, "forget/ignore previous X" phrasing, mostly English with some German) — not a claim of covering every real-world injection technique. No deduplication/near-duplicate-leakage check was performed against this project's own 12 hand-authored `prompt_injection_cases.json` examples (both sets are small enough, and structurally different enough — hand-authored vs. crowd-collected — that meaningful overlap is unlikely, but this was not formally verified).
**Intended use:** a real, held-out benchmark for `PromptInjectionEvaluator` (both the original keyword-list version and the new embedding k-NN detector) — see `docs/EVALUATION/EVALUATOR_RESULTS.md` for the measured results this produced (a real 98.5% false-negative rate on the keyword baseline, motivating the k-NN detector).

### Pipeline

`data/external/deepset_prompt_injections/fetch_and_normalize.py` — the RAW fetch (via `huggingface_hub.hf_hub_download` at the pinned revision) and PROCESSED normalization (into this project's per-record schema: `case_id`, `query`, `expected_label`, `split`, `source_label`, `provenance`, `source_dataset`, `source_revision`, `source_license`) are the same script; its output, `prompt_injections_normalized.json` (662 records, no PII, small enough and permissively licensed enough to commit directly), is the committed artifact. Re-run the script to reproduce it from source.

## Not Yet Pursued

A public bias/fairness dataset (e.g. `walledai/BBQ`, CC-BY-4.0, checked and confirmed to exist on Hugging Face) was investigated for expanding the Bias evaluator beyond its current 8 hand-authored pairs, but not integrated this milestone: BBQ's format (ambiguous/disambiguated multiple-choice QA with a bias-relevant answer option) does not map directly onto `controlplane.evaluation.bias.BiasEvaluator`'s paired-free-text-answer comparison design — integrating it well would require either a real adapter (generating real answers to BBQ's QA format and scoring which option was implied) or a different bias-evaluation mechanism, more work than fit alongside this milestone's other deliverables. Documented as a candidate for a future milestone in `docs/PROJECT_STATE/FUTURE_WORK.md`, not silently dropped.
