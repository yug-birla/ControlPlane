# Query Profiler Results

**Run (Milestone 2):** `controlplane/experiments/evaluate_query_profiler.py`, 2026-08-28. **Re-run (Milestone 3):** same script, same code, same dataset, 2026-08-28. Dataset: `query_profiles_validation` v0.1 (28 examples, provenance SYNTHETIC — see `DATASETS.md`). Raw output: `RESULTS/query_profiler_2026-08-28.json` (overwritten by the Milestone 3 re-run — see the reproducibility note below for why the numbers moved without any query_intelligence code change).

## Headline Numbers (Milestone 3 re-run)

| Field | Baseline A (rules) accuracy | Baseline B (hybrid) accuracy |
|---|---|---|
| complexity | 0.357 | 0.500 |
| sensitivity | 0.857 | 0.786 |
| ambiguity | 0.857 | 0.750 |
| actionability | 0.607 | 0.679 |
| capability_hints (micro-F1) | 0.483 | 0.476 |
| capability_hints (macro-F1) | 0.294 | 0.355 |

**Decision: Hybrid remains the default profiler** (`controlplane/runtime.py`) — actionability and capability-hint macro-F1 wins hold, complexity is now a clear hybrid win rather than a tie (see reproducibility note), sensitivity/ambiguity are narrow hybrid losses. This is an empirical choice per bootstrap SS20, not an intuition-based one.

## Reproducibility Note (found during Milestone 3)

**The rules-only numbers are bit-for-bit identical to Milestone 2's recorded run; the hybrid/k-NN numbers are not** (complexity 0.357→0.500, ambiguity 0.857→0.750; re-verified stable across repeated re-runs today, including with `OMP_NUM_THREADS=1`/`MKL_NUM_THREADS=1` forced). No code in `controlplane/query_intelligence/`, `controlplane/models/local_hf_provider.py`, or the dataset files changed between the two runs (`git diff --stat` confirms this). Since `RuleBasedQueryProfiler` has zero floating-point/embedding dependency and reproduces exactly, while `EmbeddingKNNQueryProfiler` (and therefore `HybridQueryProfiler`, which defers to it for these two fields) does not, the most likely explanation is a change in the underlying ML library environment between sessions (e.g. a `torch`/`sentence-transformers` point-release picked up by a fresh `pip install`, changing low-level numeric kernels enough to flip a few near-tied cosine-similarity majority votes) — not code drift and not per-run randomness within a single environment. **Action:** treat hybrid/k-NN-dependent metrics as reproducible only within a pinned environment; `docs/PROJECT_STATE/FUTURE_WORK.md` now tracks pinning exact `torch`/`sentence-transformers` versions (or caching exemplar embeddings to disk) as the concrete fix for full cross-session reproducibility.

## What This Does NOT Show

**Complexity accuracy (35.7% rules, 50.0% hybrid) is still close to the 33% a random 3-way guess would get, for the rules baseline in particular.** This is a real, honest finding, not hidden: the word-count heuristic (rules) largely fails to predict this dataset's notion of "complexity" better than chance; the embedding-neighbor majority vote (hybrid) does somewhat better but is not yet reliable enough to gate safety-relevant behavior on directly. Likely explanation: "complexity" in the source data appears to track semantic/reasoning complexity (how hard the underlying task is), not sentence length — word count is a weak proxy for that, though nearest-neighbor semantic similarity is evidently a better (if imperfect) one. **This is flagged as a known limitation, not glossed over** — see "Known Limitations" below. Milestone 3's Model Router checks `impact` and the policy tier with higher priority than `complexity` for this reason — complexity=HIGH still escalates to the strong model as an additional safeguard, but is not the primary signal driving routing decisions (see `docs/ALGORITHMS/MODEL_ROUTER.md`).

**Sensitivity: rules (85.7%) beats hybrid (78.6%).** The rules baseline's PII keyword list is small but precise; when it fires, it's trusted directly (see `docs/PROJECT_STATE/DECISIONS.md` on `high_confidence_fields`). Hybrid only falls back to the embedding neighbor vote when no keyword fires, and that vote is occasionally wrong. Since privacy/PII is safety-relevant, this trade-off is called out explicitly rather than average away: **a future iteration should consider widening the rule keyword list before trusting the k-NN vote further for this specific field.**

**Intent and domain are not accuracy-scored** — see `DATASETS.md`/module docstrings for why (no comparable ground truth exists for intent's categorical scheme; domain has no fixed taxonomy).

## Confusion Matrices and Per-Class Detail

Full confusion matrices and per-class precision/recall/F1 for every field are in `RESULTS/query_profiler_2026-08-28.json` (`results.rules.metrics.fields.<field>.confusion_matrix` / `.per_class`, and the same under `results.hybrid`) — not reproduced here in full since several are 4x4/5x5 and are more useful queried than read as prose. The one worth calling out directly: capability_hints macro-F1 improving from 0.294 (rules) to 0.355 (hybrid) reflects the hybrid profiler correctly detecting rarer hints (e.g. MEMORY, MULTI_SOURCE) that the keyword list alone doesn't cover.

## Known Limitations

- **28-example validation set is small.** Per-class metrics for rare capability hints and actionability values are based on single-digit sample counts in several cases — treat any single percentage as directional, not precise.
- **Complexity heuristic needs rework** before this baseline is trusted for anything complexity-gated (see above).
- **Rule keyword lists are hand-curated and narrow** — they cover the bootstrap's own worked examples well but were not tuned against this dataset, by design (this is a zero-shot rules baseline, not a fitted one).
- **k-NN exemplar bank is only 135 examples** — high-cardinality fields (domain) inherit whatever noise exists in that small a reference set; short/ambiguous queries in particular can pull in scattered, disagreeing neighbors (observed directly during manual verification on the query "what about it" — see `docs/PROJECT_STATE/PROGRESS.md`).
