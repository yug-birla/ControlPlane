"""Sequential vs. parallel execution using REAL SQL + RAG capabilities
(not simulated latency) -- supersedes
controlplane/experiments/benchmark_graph_execution.py's simulated-latency
benchmark for the "does parallelism help with real work" question, per
this milestone's explicit instruction: "Do not use artificial 200ms
latency for the final performance claim... If the underlying capability
is still mocked, label the result SIMULATED/MOCK BENCHMARK." SQL and RAG
are real as of this milestone (controlplane/capabilities/), so this
benchmark's numbers are real capability latency, not simulated.

The old simulated benchmark (docs/EVALUATION/EXECUTION_GRAPH_RESULTS.md)
is kept as-is -- it measured the Graph Executor's own concurrency
mechanics, which is still a valid, separate thing to have measured.

Run:
    .venv/Scripts/python -m controlplane.experiments.benchmark_real_capability_execution
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.capabilities.rag_capability import RAGCapability
from controlplane.capabilities.sql_capability import SQLCapability
from controlplane.execution.executor import GraphExecutor
from controlplane.execution.graph import ExecutionGraph, ExecutionNode
from controlplane.experiments.tracking import current_hardware, record_benchmark, record_evaluation, record_experiment, record_run

_QUERY = "What was our Q4 department revenue, and according to the travel policy document what are the meal expense limits?"
_TRIALS = 10


def _build_graph() -> ExecutionGraph:
    return ExecutionGraph([
        ExecutionNode(node_id="data_sql", capability="SQL"),
        ExecutionNode(node_id="data_rag", capability="RAG"),
        ExecutionNode(node_id="merge", capability="merge", depends_on=("data_sql", "data_rag")),
    ])


def run_trials(mode: str, trials: int = _TRIALS) -> list[float]:
    sql_cap = SQLCapability()
    rag_cap = RAGCapability()
    handlers = {
        "SQL": lambda node: sql_cap.execute(_QUERY),
        "RAG": lambda node: rag_cap.execute(_QUERY),
    }
    executor = GraphExecutor(handlers=handlers)
    latencies = []
    for _ in range(trials):
        graph = _build_graph()
        result = executor.run(graph, mode=mode)
        assert result.succeeded, f"benchmark trial failed unexpectedly: {result.failed}"
        latencies.append(result.total_latency_ms)
    return latencies


def _warm_caches() -> None:
    """One untimed execution before any measured trial. Without this, the
    embedding model load + first-call embedding computation (a multi-
    second one-time cost, cached process-wide afterward) lands entirely
    inside whichever mode runs first, making that mode look far slower
    than the other for a reason that has nothing to do with sequential
    vs. parallel execution. Found via a first run of this script that
    reported an implausible 42x speedup -- diagnosed as exactly this
    cold-start asymmetry before trusting the number."""
    SQLCapability().execute(_QUERY)
    RAGCapability().execute(_QUERY)


def main() -> None:
    _warm_caches()
    sequential = run_trials("sequential")
    parallel = run_trials("parallel")

    seq_mean = sum(sequential) / len(sequential)
    par_mean = sum(parallel) / len(parallel)
    speedup = seq_mean / par_mean if par_mean else None

    metrics = {
        "sample_count": _TRIALS,
        "query": _QUERY,
        "capabilities": "SQL (SQLite, real) + RAG (dense+BM25 retrieval over 30 real documents, real)",
        "sequential_latency_ms": {"mean": seq_mean, "min": min(sequential), "max": max(sequential)},
        "parallel_latency_ms": {"mean": par_mean, "min": min(parallel), "max": max(parallel)},
        "speedup": speedup,
        "failure_rate": 0.0,
        "note": "Real capability latency (SQLite query + dense/BM25 retrieval), not simulated -- see module docstring.",
    }
    print(f"REAL CAPABILITIES: sequential_mean={seq_mean:.1f}ms parallel_mean={par_mean:.1f}ms speedup={speedup:.2f}x")

    experiment_id = record_experiment(
        experiment_name="real_capability_sequential_vs_parallel",
        component="execution_graph",
        algorithm="graph_executor_bounded_concurrency",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id="nexaconsult_enterprise+synthetic_enterprise_documents",
        dataset_version="v1",
        configuration={"trials": _TRIALS, "query": _QUERY},
        notes="Real SQL + RAG capability latency, not simulated.",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)
    record_benchmark(
        model_key="sql_rag_capabilities",
        benchmark_name="real_sequential_vs_parallel",
        device=current_hardware()["device"],
        latency_ms_p50=par_mean,
        notes=json.dumps({"sequential_mean_ms": seq_mean, "parallel_mean_ms": par_mean, "speedup": speedup}),
    )

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"real_capability_execution_benchmark_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
