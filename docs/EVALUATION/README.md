# docs/EVALUATION/

Human-written summaries of experiments that are actually run, per the Milestone 2 requirement that every test/matrix/benchmark/evaluation result be documented, not just printed to a terminal.

**Source of truth:** `controlplane/experiments/tracking.py` persists every experiment/run/result to Postgres (`experiments`, `experiment_runs`, `evaluation_results`, `model_benchmarks`). The files in this folder and in `RESULTS/` are generated from those runs — if a number appears here, it was measured by running the corresponding script in `controlplane/experiments/`, not typed in by hand.

| File | What it covers |
|---|---|
| `DATASETS.md` | The datasets used for evaluation this milestone, their versions, and provenance |
| `QUERY_PROFILER_RESULTS.md` | Baseline A (rules) vs Baseline B (hybrid) accuracy/F1/confusion matrices |
| `RISK_PROFILER_RESULTS.md` | Risk severity accuracy and high-risk false-negative analysis |
| `MODEL_BENCHMARKS.md` | Local embedding model latency (cold/warm, p50/p95/p99) and the local-vs-remote comparison |
| `ROUTING_RESULTS.md` | Capability Router restriction/coverage results, Model Router action distribution + safety invariant (Milestone 3) |
| `EXECUTION_GRAPH_RESULTS.md` | Sequential vs. parallel Graph Executor benchmark, simulated latency (Milestone 3) |
| `RAG_RESULTS.md` | RAG adequacy calibration, retrieval verification, the prompt-grounding fix (Milestone 4/5), cross-encoder reranker comparison (Milestone 6) |
| `CONTROL_LOOP_RESULTS.md` | Decision/Intervention/Replan/Verification before-after + counterfactual results, real end-to-end scenario traces (Milestone 5); CONFLICTING-evidence scenario (Milestone 6) |
| `EVALUATOR_RESULTS.md` | Deterministic vs. Local Judge vs. Remote Judge calibration, Bias paired-comparison results (Milestone 6) |
| `AGENT_GOVERNANCE_RESULTS.md` | Agent/Tool Governance gate accuracy against real trajectory labels (Milestone 6) |
| `TRUST_RESULTS.md` | Why the Trust Layer has no accuracy benchmark, and what was unit-tested instead (Milestone 6) |
| `RESULTS/` | Raw JSON exports, named `<experiment>_<date>.json`, one file per experiment per day (a same-day re-run overwrites that day's file — a real limitation of the current date-only naming, not yet fixed). |

**Reproduce any result:**
```
docker compose up -d postgres
.venv/Scripts/python -m controlplane.experiments.evaluate_query_profiler
.venv/Scripts/python -m controlplane.experiments.evaluate_risk_profiler
.venv/Scripts/python -m controlplane.experiments.benchmark_local_model
.venv/Scripts/python -m controlplane.experiments.compare_local_vs_remote
.venv/Scripts/python -m controlplane.experiments.evaluate_capability_router
.venv/Scripts/python -m controlplane.experiments.evaluate_model_router
.venv/Scripts/python -m controlplane.experiments.benchmark_graph_execution
.venv/Scripts/python -m controlplane.experiments.benchmark_real_capability_execution
.venv/Scripts/python -m controlplane.experiments.evaluate_rag_adequacy
.venv/Scripts/python -m controlplane.experiments.evaluate_reranker
.venv/Scripts/python -m controlplane.experiments.evaluate_control_loop_before_after
.venv/Scripts/python -m controlplane.experiments.evaluate_agent_governance
# Slow (~15-25 min each -- CPU-only Local Judge inference):
.venv/Scripts/python -m controlplane.experiments.evaluate_judge_calibration
.venv/Scripts/python -m controlplane.experiments.evaluate_bias
# Requires live keys, otherwise NOT_MEASURED:
GEMINI_API_KEY_1=... .venv/Scripts/python -m controlplane.experiments.compare_groq_vs_gemini
```
Each run's `code_commit` (git SHA) and `hardware` are recorded in `experiment_runs`, so a result can always be traced back to the exact code and machine it came from.
