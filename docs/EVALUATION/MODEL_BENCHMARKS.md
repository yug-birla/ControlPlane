# Model Benchmarks

## Local Embedding Model Latency

**Run:** `controlplane/experiments/benchmark_local_model.py`, 2026-08-28. Model: `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Device: CPU (Intel i7-13620H, 10 cores/16 threads, 15.7GB RAM, no discrete GPU — see `docs/PROJECT_STATE/DECISIONS.md` for the hardware-inspection record this model selection was based on).

| Metric | Value |
|---|---|
| Cold start (process start -> first embedding, includes model load) | 20,140 ms |
| Warm latency, average (single query) | 19.8 ms |
| Warm latency, p50 | 16.0 ms |
| Warm latency, p95 | 32.0 ms |
| Warm latency, p99 | 47.0 ms |
| Throughput (single-threaded, sequential, no batching) | 50.5 QPS |
| Sample size | 30 warm iterations |

**Cold start is dominated by one-time process/model-load overhead** (torch import, model weight loading) — it does not recur within a process's lifetime (`controlplane/query_intelligence/knn_profiler.py` caches the provider with `@lru_cache`, fixed after an initial implementation bug where it reloaded the model on every call — see `docs/PROJECT_STATE/PROGRESS.md`). A long-running API process pays this cost once at first use, not per-request.

## Local vs. Remote Query Classification Comparison

**Run:** `controlplane/experiments/compare_local_vs_remote.py`, 2026-08-28. Test set: first 10 `query_profiles_validation` examples (deterministic, not cherry-picked). Raw output: `RESULTS/local_vs_remote_2026-08-28.json`.

| Method | Cost | Avg latency | complexity | sensitivity | ambiguity | actionability |
|---|---|---|---|---|---|---|
| Local (embedding k-NN) | free | 2,127 ms* | 0.30 | 0.70 | 0.80 | 0.90 |
| Remote (Groq-prompted) | metered | **NOT MEASURED** | **NOT MEASURED** | **NOT MEASURED** | **NOT MEASURED** | **NOT MEASURED** |

**\*** This average includes one cold-start call within the 10-query batch (first call in a fresh process); see the dedicated warm-latency benchmark above (16-47ms) for steady-state performance — this comparison script was not optimized to separate the two, since its purpose is the local-vs-remote comparison, not a latency micro-benchmark.

**Remote side: NOT MEASURED.** `GROQ_API_KEY` was not available in the environment this comparison was run in (it is never persisted between sessions — see `docs/PROJECT_STATE/DECISIONS.md` — and was not re-supplied for this milestone). Milestone 1 already live-validated Groq connectivity and correctness independently (`docs/ALGORITHMS/MODEL_PROVIDER_ABSTRACTION.md` SS16); this specific classification-quality/cost/latency comparison has not been run. The harness (`compare_local_vs_remote.py`) is real, tested code, ready to run the moment a key is supplied — this is a reporting gap, not a missing capability.

**To actually run this comparison:**
```
GROQ_API_KEY=... GROQ_MODEL=... .venv/Scripts/python -m controlplane.experiments.compare_local_vs_remote
```
