"""Latency benchmark for the local embedding model -- bootstrap SS26.
Cold-start (first call, includes model load + exemplar bank embedding),
then N warm calls for p50/p95/p99. Persists to ``model_benchmarks``.

Run:
    .venv/Scripts/python -m controlplane.experiments.benchmark_local_model
"""

from __future__ import annotations

import time

from controlplane.experiments.tracking import record_benchmark
from controlplane.models.local_hf_provider import MODEL_REPO

_WARM_ITERATIONS = 30
_SAMPLE_QUERY = "What was our Q4 revenue compared to last year?"


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))
    return ordered[idx]


def main() -> None:
    from controlplane.models.local_hf_provider import LocalHFEmbeddingProvider

    cold_start = time.monotonic()
    provider = LocalHFEmbeddingProvider()
    provider.embed(text=_SAMPLE_QUERY)  # first real inference, included in cold_start
    cold_start_ms = (time.monotonic() - cold_start) * 1000

    warm_latencies = []
    for _ in range(_WARM_ITERATIONS):
        start = time.monotonic()
        provider.embed(text=_SAMPLE_QUERY)
        warm_latencies.append((time.monotonic() - start) * 1000)

    p50 = _percentile(warm_latencies, 0.50)
    p95 = _percentile(warm_latencies, 0.95)
    p99 = _percentile(warm_latencies, 0.99)
    avg_warm = sum(warm_latencies) / len(warm_latencies)
    throughput_qps = 1000.0 / avg_warm if avg_warm else None

    print(f"cold_start_ms={cold_start_ms:.1f}")
    print(f"warm avg_ms={avg_warm:.2f} p50={p50:.2f} p95={p95:.2f} p99={p99:.2f} n={_WARM_ITERATIONS}")
    print(f"throughput_qps (single-threaded, sequential)={throughput_qps:.1f}")

    record_benchmark(
        model_key="local_hf_all_minilm_l6_v2",
        benchmark_name="single_query_embedding_latency",
        device="cpu",
        latency_ms_p50=p50,
        latency_ms_p95=p95,
        latency_ms_p99=p99,
        cold_start_ms=cold_start_ms,
        warm_latency_ms=avg_warm,
        throughput_qps=throughput_qps,
        notes=f"model={MODEL_REPO}, n_warm_iterations={_WARM_ITERATIONS}, single-threaded sequential (no batching)",
    )
    print("Recorded to model_benchmarks.")


if __name__ == "__main__":
    main()
