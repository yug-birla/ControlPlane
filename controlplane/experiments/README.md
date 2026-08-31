# controlplane/experiments/

**Purpose:** experiment/evaluation tracking and the evaluation scripts themselves. Every experiment this milestone (and future ones) runs through `tracking.py` so results are persisted in Postgres, not just printed  -  see `docs/EVALUATION/README.md`.

## Interface

- `tracking.py`: `record_experiment`/`record_run`/`record_evaluation`/`record_benchmark`  -  the only way experiment data reaches `experiments`/`experiment_runs`/`evaluation_results`/`model_benchmarks`.
- `metrics.py`: dependency-free classification metrics (accuracy, per-class P/R/F1, confusion matrix, multi-label micro/macro F1, false-negative rate)  -  no scikit-learn.
- `evaluate_query_profiler.py`, `evaluate_risk_profiler.py`, `benchmark_local_model.py`, `compare_local_vs_remote.py`, `evaluate_capability_router.py`, `evaluate_model_router.py`, `benchmark_graph_execution.py`, `benchmark_real_capability_execution.py`, `evaluate_rag_adequacy.py`, `compare_groq_vs_gemini.py`, `evaluate_control_loop_before_after.py`: runnable scripts (`python -m controlplane.experiments.<name>`) that produce the numbers in `docs/EVALUATION/`.

### The central product experiment (Milestone 9)

- `evaluate_baseline_vs_controlplane.py`  -  **the headline experiment.** Unmanaged baseline AI vs. full ControlPlane on REAL local model output, identical scoring for both. Supersedes `evaluate_control_loop_before_after.py` as *product* evidence (that one used scripted responses and remains the *mechanism* evidence). See `docs/EVALUATION/BASELINE_VS_CONTROLPLANE.md`.
- `evaluate_ablations.py`  -  component ablations on the same dataset/scoring: baseline vs. no-corpus-affinity (= the Milestone 8 system) vs. no-enforcement (Shadow Mode) vs. full. Answers "did the routing fix matter?" and "does *enforcing* add anything over *detecting*?".
- `evaluate_corpus_affinity.py`  -  calibrates and evaluates semantic RAG routing against the keyword baseline, with a strict calibration/held-out split.
- `rescore_results.py`  -  re-scores saved result files with the current scoring code **without re-running inference**. Exists because two real bugs were found in the scoring harness itself; committed so the correction is reproducible rather than hand-edited.

Note on runtime: the experiments that generate text use the local CPU-only provider (~30-90s per request), so a full baseline-vs-ControlPlane run takes tens of minutes and the 3-condition ablation takes longer. Run them in the background.

## Dependencies

Postgres (via `controlplane.db`), the query intelligence / risk / models packages being evaluated.

## Limitations

`current_code_commit()` shells out to `git rev-parse HEAD`  -  returns `None` outside a git repo or if git isn't on PATH, never fabricates a commit hash.

## Extension points

Future milestones' evaluations (RAG adequacy, model routing quality, intervention accuracy) use the same `tracking.py` functions rather than inventing a second persistence path.
