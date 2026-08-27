# Datasets Used for Milestone 2 Evaluation

| dataset_id | file | version | split | examples | annotation_source |
|---|---|---|---|---|---|
| `query_profiles_train` | `data/evaluation/train/query_profiles_train.json` | v0.1 | train | 135 | SYNTHETIC |
| `query_profiles_validation` | `data/evaluation/validation/query_profiles_validation.json` | v0.1 | validation | 28 | SYNTHETIC |

**Version** is the schema version from `docs/DATA/DATA_CHANGELOG.md` (v0.1, frozen 2026-08-26), not a dataset-content version — the file contents have not changed since generation.

**Annotation source: SYNTHETIC.** Every label in both files was LLM-generated during the 2026-08-26 data-generation pass (`docs/DATA/DATASET_GAPS.md`), not human-annotated. Per bootstrap SS17 ("Never treat LLM-generated labels as automatically equivalent to human ground truth"), every accuracy/F1 number in `QUERY_PROFILER_RESULTS.md` and `RISK_PROFILER_RESULTS.md` measures **agreement with another model's synthetic judgment**, not agreement with human ground truth. Treat these as directional signals for comparing baselines against each other, not as an absolute correctness claim.

**Test/challenge splits (30 and 77 examples) were not used this milestone** — they remain held out per `docs/DATA/EVALUATION_PROTOCOL.md`'s protection rule, for a later, more consequential evaluation (e.g. once real human annotation exists, or when comparing against a learned model in a later milestone).

**Train/validation separation:** the k-NN baseline's exemplar bank (`controlplane/query_intelligence/exemplar_bank.py`) is built exclusively from the train split; all accuracy numbers are measured on the validation split, which the exemplar bank never sees. This is basic ML hygiene, not a novel practice, but is stated explicitly since it would otherwise be easy to accidentally leak information between the "reference data" and "test data" for a k-NN method (there's no training step to notice the leak at).
