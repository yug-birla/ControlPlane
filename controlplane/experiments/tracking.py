"""Experiment/evaluation persistence -- bootstrap Milestone 2 SS15-17.

Every experiment run this milestone goes through this module so results
land in Postgres (``experiments``/``experiment_runs``/``evaluation_results``/
``model_benchmarks``), not just printed to a terminal. ``docs/EVALUATION/``
holds the human-written summaries and raw JSON exports of what's recorded
here -- this module is the single source both are generated from.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from controlplane.db.engine import session_scope
from controlplane.db.models import (
    EvaluationResultRecord,
    ExperimentRecord,
    ExperimentRunRecord,
    ModelBenchmarkRecord,
    new_id,
)

NOT_MEASURED = "NOT_MEASURED"


def current_code_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=__file__.rsplit("controlplane", 1)[0], text=True
        ).strip()
    except Exception:
        return None


def current_hardware() -> dict:
    import platform

    return {
        "cpu": platform.processor() or "unknown",
        "os": platform.platform(),
        "python": platform.python_version(),
        "device": "cpu",
    }


def record_experiment(*, experiment_name: str, component: str, algorithm: str, algorithm_version: str) -> str:
    experiment_id = new_id("exp")
    with session_scope() as session:
        session.add(
            ExperimentRecord(
                id=experiment_id,
                experiment_name=experiment_name,
                component=component,
                algorithm=algorithm,
                algorithm_version=algorithm_version,
            )
        )
    return experiment_id


def record_run(
    *,
    experiment_id: str,
    dataset_id: str,
    dataset_version: str,
    model: str | None = None,
    configuration: dict | None = None,
    status: str = "SUCCESS",
    notes: str | None = None,
) -> str:
    run_id = new_id("run")
    with session_scope() as session:
        session.add(
            ExperimentRunRecord(
                id=run_id,
                experiment_id=experiment_id,
                run_at=datetime.now(timezone.utc),
                model=model,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                configuration=configuration or {},
                hardware=current_hardware(),
                code_commit=current_code_commit(),
                status=status,
                notes=notes,
            )
        )
    return run_id


def record_evaluation(*, experiment_run_id: str, split: str | None, metrics: dict) -> str:
    result_id = new_id("evalres")
    with session_scope() as session:
        session.add(
            EvaluationResultRecord(
                id=result_id,
                experiment_run_id=experiment_run_id,
                split=split,
                metrics=metrics,
            )
        )
    return result_id


def record_benchmark(
    *,
    model_key: str,
    benchmark_name: str,
    device: str,
    latency_ms_p50: float | None = None,
    latency_ms_p95: float | None = None,
    latency_ms_p99: float | None = None,
    cold_start_ms: float | None = None,
    warm_latency_ms: float | None = None,
    throughput_qps: float | None = None,
    notes: str | None = None,
) -> str:
    benchmark_id = new_id("bench")
    with session_scope() as session:
        session.add(
            ModelBenchmarkRecord(
                id=benchmark_id,
                model_key=model_key,
                benchmark_name=benchmark_name,
                latency_ms_p50=latency_ms_p50,
                latency_ms_p95=latency_ms_p95,
                latency_ms_p99=latency_ms_p99,
                cold_start_ms=cold_start_ms,
                warm_latency_ms=warm_latency_ms,
                throughput_qps=throughput_qps,
                device=device,
                notes=notes,
            )
        )
    return benchmark_id
