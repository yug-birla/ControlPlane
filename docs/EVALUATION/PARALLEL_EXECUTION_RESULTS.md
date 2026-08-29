# Parallel Execution on Real Capabilities

**Run:** `controlplane/experiments/benchmark_parallel_capabilities.py`, 2026-08-29.
**Raw:** `docs/EVALUATION/RESULTS/parallel_capabilities_2026-08-29.json`
**Scale:** `SMOKE_TEST` — 3 queries × 3 trials × 2 modes, one machine, warm-up excluded.

## Why this exists alongside the older benchmark

`benchmark_graph_execution.py` (Milestone 3) measured the wave scheduler against **simulated** node work using sleeps, and reported a 1.96× speedup. That proved the scheduler is correct, but the speedup number was an artefact of the experimenter choosing two balanced sleep durations. It could not say whether parallelism helps on the real capability mix.

This runs the same graph through the same executor in both modes with the **real** RAG (dense + BM25 + RRF + cross-encoder over the 30-document corpus) and the **real** SQL capability (SQLite over the enterprise demo database).

## Result

| Metric | Sequential | Parallel |
|---|---|---|
| Wall time, mean | 545.1 ms | **432.3 ms** |
| Wall time, median | 469.0 ms | 406.0 ms |
| Wall time, p95 | 672.0 ms | 547.0 ms |
| Critical path, mean | 428.8 ms | 430.7 ms |

**Measured speedup: 1.26×**
**Critical-path ceiling: 1.27×**

## Interpretation — the honest reading

**The scheduler achieves ~99% of the maximum speedup available to it.** No scheduler can beat the longest dependency chain, and here that ceiling is only 1.27× because the two branches are badly unbalanced: RAG (embedding + BM25 + cross-encoder reranking) dominates, while SQL returns quickly. Running a fast branch beside a slow one hides the fast branch's cost and nothing more — that is Amdahl's law, not a defect.

Reporting the ceiling next to the measurement is the point. **1.26× looks unimpressive against the older benchmark's 1.96×, and is actually the better result**: the older number came from two artificially balanced sleeps, whereas this one is at the real ceiling for a real workload.

## Where parallelism would matter more

- **More independent branches.** RAG + SQL + CHAT_HISTORY + MEMORY gives the scheduler more to overlap. Three of those four are currently `MOCKED`, so this cannot be measured yet.
- **Balanced branch latencies.** The gain is bounded by `slowest / (sum of all)`; two similar-cost branches approach 2×.
- **Multi-agent fan-out** (§39), where several agents each invoke a capability — not yet built, since the default router still emits at most one AGENT node.

## Threats to validity, stated

- **The GIL.** These capabilities are NumPy/torch (releases the GIL) and SQLite I/O (releases it), so threads genuinely overlap. A pure-Python capability would show no gain. The measurement does not generalize to arbitrary capabilities.
- **`SMOKE_TEST` scale.** 9 measurements per mode on one machine, with other work running in this session. Treat the ratio as indicative and the absolute milliseconds as environment-specific.
- **Warm-up excluded** so one-time model loading is not attributed to whichever mode ran first — that would have been a ~20-second artefact dwarfing the entire effect.
