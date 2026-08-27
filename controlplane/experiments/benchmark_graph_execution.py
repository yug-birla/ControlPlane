"""Sequential vs. parallel Execution Graph benchmark --
docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md SS54 / bootstrap SS61
("Implement at least one valid multi-source workflow... Run SEQUENTIAL
and PARALLEL. Measure total latency, branch latency, speedup, failure
rate, sample count.").

This benchmarks the Graph Executor's own concurrency mechanics using a
SQL+RAG-shaped graph with simulated per-node latency -- SQL/RAG have no
real implementation yet (Layer 5/11, see
docs/PROJECT_STATE/FUTURE_WORK.md), so there is no real capability
latency to measure. The simulated latency (a fixed sleep per data node)
stands in for "some real, non-trivial I/O-bound capability call" purely
to give the executor's dependency/concurrency handling something
measurable to run against. This is a benchmark of the executor, not a
claim about real SQL/RAG performance -- see the note in every result.

Run:
    .venv/Scripts/python -m controlplane.experiments.benchmark_graph_execution
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.execution.executor import GraphExecutor
from controlplane.execution.graph import ExecutionGraph, ExecutionNode
from controlplane.experiments.tracking import current_hardware, record_benchmark, record_evaluation, record_experiment, record_run

_SIMULATED_NODE_LATENCY_S = 0.2
_TRIALS = 10


def _simulated_data_handler(node: ExecutionNode) -> dict:
    time.sleep(_SIMULATED_NODE_LATENCY_S)
    return {"status": "SIMULATED", "note": "stands in for a real SQL/RAG call -- not yet implemented"}


def _build_graph() -> ExecutionGraph:
    return ExecutionGraph([
        ExecutionNode(node_id="data_sql", capability="SQL"),
        ExecutionNode(node_id="data_rag", capability="RAG"),
        ExecutionNode(node_id="merge", capability="merge", depends_on=("data_sql", "data_rag")),
        ExecutionNode(node_id="generation", capability="generation", depends_on=("merge",)),
    ])


def run_trials(mode: str, trials: int = _TRIALS) -> list[float]:
    handlers = {
        "SQL": _simulated_data_handler,
        "RAG": _simulated_data_handler,
        "generation": lambda node: {"content": "simulated answer"},
    }
    executor = GraphExecutor(handlers=handlers)
    latencies = []
    for _ in range(trials):
        graph = _build_graph()
        result = executor.run(graph, mode=mode)
        assert result.succeeded, f"benchmark trial failed unexpectedly: {result.failed}"
        latencies.append(result.total_latency_ms)
    return latencies


def main() -> None:
    sequential = run_trials("sequential")
    parallel = run_trials("parallel")

    seq_mean = sum(sequential) / len(sequential)
    par_mean = sum(parallel) / len(parallel)
    speedup = seq_mean / par_mean if par_mean else None

    metrics = {
        "sample_count": _TRIALS,
        "simulated_node_latency_ms": _SIMULATED_NODE_LATENCY_S * 1000,
        "graph_shape": "data_sql + data_rag (parallel, no real capability) -> merge -> generation",
        "sequential_latency_ms": {"mean": seq_mean, "min": min(sequential), "max": max(sequential)},
        "parallel_latency_ms": {"mean": par_mean, "min": min(parallel), "max": max(parallel)},
        "speedup": speedup,
        "failure_rate": 0.0,
        "note": (
            "Measures the Graph Executor's own concurrency handling using simulated "
            "per-node latency, since SQL/RAG have no real implementation yet "
            "(Layer 5/11). Not a measurement of real SQL/RAG/model latency."
        ),
    }
    print(f"sequential_mean={seq_mean:.1f}ms parallel_mean={par_mean:.1f}ms speedup={speedup:.2f}x")

    experiment_id = record_experiment(
        experiment_name="execution_graph_sequential_vs_parallel",
        component="execution_graph",
        algorithm="graph_executor_bounded_concurrency",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id="synthetic_graph_benchmark",
        dataset_version="v1",
        configuration={"trials": _TRIALS, "simulated_node_latency_s": _SIMULATED_NODE_LATENCY_S},
        notes="Simulated capability latency -- see module docstring.",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)
    record_benchmark(
        model_key="execution_graph_executor",
        benchmark_name="sequential_vs_parallel",
        device=current_hardware()["device"],
        latency_ms_p50=par_mean,
        notes=json.dumps({"sequential_mean_ms": seq_mean, "parallel_mean_ms": par_mean, "speedup": speedup}),
    )

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"execution_graph_benchmark_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
