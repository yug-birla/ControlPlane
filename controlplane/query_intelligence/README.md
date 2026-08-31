# controlplane/query_intelligence/

**Purpose:** the Query Profiler  -  turns a raw query into a `QueryFingerprint`. See `docs/ALGORITHMS/QUERY_PROFILER_BASELINE.md` for the full design and `docs/EVALUATION/QUERY_PROFILER_RESULTS.md` for measured accuracy.

## Interface

- `fingerprint.py`: `QueryFingerprint` and its enums (`Intent`, `Complexity`, `Sensitivity`, `Ambiguity`, `Impact`, `Actionability`, `DataRequirement`, `CapabilityHint`).
- `rules.py`: `RuleBasedQueryProfiler` (Baseline A, no model, no dependencies beyond stdlib).
- `exemplar_bank.py`: loads the train-split labeled queries and their embeddings (cached per-process).
- `knn_profiler.py`: `EmbeddingKNNQueryProfiler` (Baseline B) and `HybridQueryProfiler` (the runtime default  -  combines both).

## Dependencies

`controlplane.models.local_hf_provider` (only the k-NN/hybrid path  -  `RuleBasedQueryProfiler` has none). `data/evaluation/train/query_profiles_train.json` (exemplar bank).

## Limitations

Complexity classification is close to chance-level for both baselines (see the results doc)  -  do not gate anything safety-relevant on it yet. `intent` and `domain` are produced but not accuracy-evaluated (no comparable ground truth exists).

## Extension points

Layer 9+ (Capability/Data Routing) consumes `capability_hints`/`data_requirement` directly. A future learned classifier would implement the same `.profile(query) -> QueryFingerprint` shape as `RuleBasedQueryProfiler`/`HybridQueryProfiler`, no interface change needed.
