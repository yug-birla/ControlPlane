# Execution Graph — Sequential vs. Parallel Results

**Run:** `controlplane/experiments/benchmark_graph_execution.py`, 2026-08-28. Hardware: CPU-only (see `docs/EVALUATION/MODEL_BENCHMARKS.md` for the full hardware spec). Raw output: `RESULTS/execution_graph_benchmark_2026-08-28.json`.

## What Was Measured

A 4-node graph shaped like the canonical multi-source example from `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` §54 (`data_sql` + `data_rag` in parallel → `merge` → `generation`), run 10 times in `mode="sequential"` and 10 times in `mode="parallel"`. Each of `data_sql`/`data_rag` sleeps 200ms to simulate a real I/O-bound capability call — **SQL/RAG have no real implementation yet** (Layer 5/11, `docs/PROJECT_STATE/FUTURE_WORK.md`), so this benchmarks the Graph Executor's own dependency/concurrency handling, not real SQL/RAG latency.

## Headline Numbers

| Metric | Sequential | Parallel |
|---|---|---|
| Mean total latency | 401.6ms | 204.6ms |
| Sample count | 10 | 10 |
| Failure rate | 0/10 | 0/10 |

**Speedup: 1.96x.** Close to the theoretical maximum (2x, since two 200ms nodes fully overlap and the shared `merge`/`generation` work is negligible) — confirms the executor actually runs independent-branch nodes concurrently rather than only appearing to.

## Interpretation

This is a real, measured property of `controlplane/execution/executor.py`'s bounded `ThreadPoolExecutor` wave scheduling — not a claim about real SQL/RAG/model latency, and not extrapolated to production traffic. The measured number that *would* need real capability implementations (Layer 5/11) to produce is "how much does parallelizing real SQL+RAG execution actually save end-to-end" — that remains **NOT MEASURED** until those capabilities exist.

## Known Limitations

- Simulated latency, not real capability latency (see above).
- No load/concurrency test under realistic multi-request traffic — this benchmark is single-request, single-process.
- `max_workers=4` (the executor's default) was not itself benchmarked against other bound values — 4 is an unvalidated default chosen for the ~10,000/week planning scale (bootstrap §34/§36's "bounded concurrency, not billions of requests" guidance), not a tuned value.
