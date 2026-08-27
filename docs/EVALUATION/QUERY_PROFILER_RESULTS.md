# Query Profiler Results

**Run:** `controlplane/experiments/evaluate_query_profiler.py`, 2026-08-28. Dataset: `query_profiles_validation` v0.1 (28 examples, provenance SYNTHETIC — see `DATASETS.md`). Raw output: `RESULTS/query_profiler_2026-08-28.json`. Code commit: see that file's `experiment_run` record (`experiment_runs.code_commit`).

## Headline Numbers

| Field | Baseline A (rules) accuracy | Baseline B (hybrid) accuracy |
|---|---|---|
| complexity | 0.357 | 0.357 |
| sensitivity | 0.857 | 0.786 |
| ambiguity | 0.857 | 0.857 |
| actionability | 0.607 | 0.679 |
| capability_hints (micro-F1) | 0.483 | 0.476 |
| capability_hints (macro-F1) | 0.294 | 0.355 |

**Decision: Hybrid is the default profiler** (`controlplane/runtime.py`), not because it wins everywhere — it doesn't — but because it wins on actionability and on capability-hint macro-F1 (which weighs rarer, harder-to-detect hints equally, and matters more for future routing than the more frequent ones), ties on ambiguity and complexity, and only loses narrowly on sensitivity (see below for why that specific loss matters and what it does not imply). This is an empirical choice per bootstrap SS20, not an intuition-based one.

## What This Does NOT Show

**Complexity accuracy (35.7% for both baselines) is barely above the 33% a random 3-way guess would get.** This is a real, honest finding, not hidden: the word-count heuristic (rules) and the embedding-neighbor majority vote (hybrid) both fail to predict this dataset's notion of "complexity" much better than chance. Likely explanation: "complexity" in the source data appears to track semantic/reasoning complexity (how hard the underlying task is), not sentence length or lexical similarity to other queries — neither baseline's signal is a good proxy for that. **This is flagged as a known limitation, not glossed over** — see "Known Limitations" below.

**Sensitivity: rules (85.7%) beats hybrid (78.6%).** The rules baseline's PII keyword list is small but precise; when it fires, it's trusted directly (see `docs/PROJECT_STATE/DECISIONS.md` on `high_confidence_fields`). Hybrid only falls back to the embedding neighbor vote when no keyword fires, and that vote is occasionally wrong. Since privacy/PII is safety-relevant, this trade-off is called out explicitly rather than average away: **a future iteration should consider widening the rule keyword list before trusting the k-NN vote further for this specific field.**

**Intent and domain are not accuracy-scored** — see `DATASETS.md`/module docstrings for why (no comparable ground truth exists for intent's categorical scheme; domain has no fixed taxonomy).

## Confusion Matrices and Per-Class Detail

Full confusion matrices and per-class precision/recall/F1 for every field are in `RESULTS/query_profiler_2026-08-28.json` (`results.rules.metrics.fields.<field>.confusion_matrix` / `.per_class`, and the same under `results.hybrid`) — not reproduced here in full since several are 4x4/5x5 and are more useful queried than read as prose. The one worth calling out directly: capability_hints macro-F1 improving from 0.294 (rules) to 0.355 (hybrid) reflects the hybrid profiler correctly detecting rarer hints (e.g. MEMORY, MULTI_SOURCE) that the keyword list alone doesn't cover.

## Known Limitations

- **28-example validation set is small.** Per-class metrics for rare capability hints and actionability values are based on single-digit sample counts in several cases — treat any single percentage as directional, not precise.
- **Complexity heuristic needs rework** before this baseline is trusted for anything complexity-gated (see above).
- **Rule keyword lists are hand-curated and narrow** — they cover the bootstrap's own worked examples well but were not tuned against this dataset, by design (this is a zero-shot rules baseline, not a fitted one).
- **k-NN exemplar bank is only 135 examples** — high-cardinality fields (domain) inherit whatever noise exists in that small a reference set; short/ambiguous queries in particular can pull in scattered, disagreeing neighbors (observed directly during manual verification on the query "what about it" — see `docs/PROJECT_STATE/PROGRESS.md`).
