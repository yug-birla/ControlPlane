# controlplane/experiments/

**Purpose:** experiment/evaluation tracking and the evaluation scripts themselves. Every experiment this milestone (and future ones) runs through `tracking.py` so results are persisted in Postgres, not just printed — see `docs/EVALUATION/README.md`.

## Interface

- `tracking.py`: `record_experiment`/`record_run`/`record_evaluation`/`record_benchmark` — the only way experiment data reaches `experiments`/`experiment_runs`/`evaluation_results`/`model_benchmarks`.
- `metrics.py`: dependency-free classification metrics (accuracy, per-class P/R/F1, confusion matrix, multi-label micro/macro F1, false-negative rate) — no scikit-learn.
- `evaluate_query_profiler.py`, `evaluate_risk_profiler.py`, `benchmark_local_model.py`, `compare_local_vs_remote.py`, `evaluate_capability_router.py`, `evaluate_model_router.py`, `benchmark_graph_execution.py`: runnable scripts (`python -m controlplane.experiments.<name>`) that produce the numbers in `docs/EVALUATION/`.

## Dependencies

Postgres (via `controlplane.db`), the query intelligence / risk / models packages being evaluated.

## Limitations

`current_code_commit()` shells out to `git rev-parse HEAD` — returns `None` outside a git repo or if git isn't on PATH, never fabricates a commit hash.

## Extension points

Future milestones' evaluations (RAG adequacy, model routing quality, intervention accuracy) use the same `tracking.py` functions rather than inventing a second persistence path.
