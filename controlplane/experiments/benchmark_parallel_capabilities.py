"""Sequential vs parallel execution of REAL capabilities.

Milestone 11 (§38/§39/§71). The existing
``benchmark_graph_execution.py`` measures the executor's own concurrency
against *simulated* node work with sleeps -- useful for proving the wave
scheduler is correct, but it cannot say whether parallelism helps on the
real capability mix, because simulated latency is chosen by the
experimenter.

This runs the SAME graph through the SAME executor in both modes with
the REAL RAG (dense + BM25 + RRF + cross-encoder over the 30-document
corpus) and the REAL SQL capability (SQLite over the enterprise demo
database).

WHAT A HONEST RESULT LOOKS LIKE HERE: RAG and SQL have very different
latencies, so the speedup is bounded by the slower branch (Amdahl), and
the ceiling is the critical path -- not 2x. Both numbers are reported so
the ceiling is visible rather than implied.

Python's GIL matters and is not hidden: these capabilities are a mix of
NumPy/torch work (which releases the GIL) and SQLite I/O (which also
releases it), so threads genuinely overlap here. A pure-Python capability
would not benefit, and that limitation is stated rather than discovered
later.

SCALE: SMOKE_TEST -- a handful of queries repeated a few times on one
machine, with a warm-up to exclude one-time model loading.

Run:
    .venv/Scripts/python -m controlplane.experiments.benchmark_parallel_capabilities
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import date
from pathlib import Path

from controlplane.capabilities.rag_capability import RAGCapability
from controlplane.capabilities.sql_capability import SQLCapability
from controlplane.execution.executor import GraphExecutor
from controlplane.execution.graph import ExecutionGraph, ExecutionNode
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_QUERIES = [
    "According to our travel policy, what is the meal reimbursement limit, "
    "and what was our Q4 department revenue?",
    "What is our data retention period, and which projects are currently active?",
    "What does the SLA guarantee, and what are the overdue invoices?",
]
_TRIALS = 3


def _build_graph() -> ExecutionGraph:
    """RAG and SQL are independent: neither depends on the other, so the
    scheduler is free to run them concurrently. merge fans them in."""
    graph = ExecutionGraph()
    graph.add_node(ExecutionNode(node_id="data_rag", capability="RAG"))
    graph.add_node(ExecutionNode(node_id="data_sql", capability="SQL"))
    graph.add_node(ExecutionNode(
        node_id="merge", capability="merge",
        depends_on=("data_rag", "data_sql"), requires_all_dependencies=False,
    ))
    graph.validate()
    return graph


def _handlers(rag: RAGCapability, sql: SQLCapability) -> dict:
    return {
        "RAG": lambda node: rag.execute(node.input_ref["query"]),
        "SQL": lambda node: sql.execute(node.input_ref["query"]),
        "merge": lambda node: {"merged": True},
    }


def _run_once(query: str, mode: str, handlers: dict) -> dict:
    graph = _build_graph()
    for node in graph.nodes:
        node.input_ref = {"query": query}
    executor = GraphExecutor(handlers=handlers, max_workers=4)
    start = time.monotonic()
    result = executor.run(graph, mode=mode)
    wall_ms = (time.monotonic() - start) * 1000
    return {
        "mode": mode,
        "wall_ms": wall_ms,
        "critical_path_ms": result.critical_path_ms,
        "completed": len(result.completed),
        "failed": len(result.failed),
        "node_latencies": {n.node_id: n.latency_ms for n in graph.nodes},
    }


def main() -> None:
    rag, sql = RAGCapability(), SQLCapability()
    handlers = _handlers(rag, sql)

    # Warm-up excluded from every measurement: the first RAG call loads
    # the embedding model and the cross-encoder, which would otherwise be
    # attributed to whichever mode happened to run first.
    print("Warming up (model loads excluded from measurements)...")
    _run_once(_QUERIES[0], "sequential", handlers)

    rows: list[dict] = []
    for query in _QUERIES:
        for trial in range(_TRIALS):
            for mode in ("sequential", "parallel"):
                row = _run_once(query, mode, handlers)
                row.update(query=query[:60], trial=trial)
                rows.append(row)
                print(f"  {mode:<11} trial={trial} wall={row['wall_ms']:>8.1f}ms "
                      f"critical_path={row['critical_path_ms'] or 0:>8.1f}ms")

    def _summary(mode: str) -> dict:
        walls = [r["wall_ms"] for r in rows if r["mode"] == mode]
        paths = [r["critical_path_ms"] or 0 for r in rows if r["mode"] == mode]
        walls_sorted = sorted(walls)
        return {
            "sample_count": len(walls),
            "wall_ms_mean": statistics.mean(walls),
            "wall_ms_median": statistics.median(walls),
            "wall_ms_p95": walls_sorted[int(len(walls_sorted) * 0.95) - 1] if walls_sorted else None,
            "critical_path_ms_mean": statistics.mean(paths) if paths else None,
        }

    seq, par = _summary("sequential"), _summary("parallel")
    speedup = seq["wall_ms_mean"] / par["wall_ms_mean"] if par["wall_ms_mean"] else None
    # The ceiling: no scheduler can beat the longest dependency chain.
    ceiling = (
        seq["wall_ms_mean"] / par["critical_path_ms_mean"]
        if par["critical_path_ms_mean"] else None
    )

    experiment_id = record_experiment(
        experiment_name="parallel_real_capabilities",
        component="execution_graph",
        algorithm="sequential_vs_parallel_wave_scheduling",
        algorithm_version="v1",
    )
    for name, metrics in (("sequential", seq), ("parallel", par)):
        run_id = record_run(
            experiment_id=experiment_id, dataset_id="parallel_capability_queries",
            dataset_version="v0.1", model=name, configuration={"mode": name, "trials": _TRIALS},
            notes="REAL RAG (dense+BM25+RRF+cross-encoder) and REAL SQL, not simulated work; "
                  "warm-up excluded; SMOKE_TEST scale",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print("\n" + "=" * 66)
    print(f"{'METRIC':<30}{'SEQUENTIAL':>17}{'PARALLEL':>17}")
    print("=" * 66)
    for key in ("wall_ms_mean", "wall_ms_median", "wall_ms_p95", "critical_path_ms_mean"):
        s, p = seq.get(key), par.get(key)
        print(f"{key:<30}{(s or 0):>17.1f}{(p or 0):>17.1f}")
    print(f"\nmeasured speedup:        {speedup:.2f}x" if speedup else "\nspeedup: NOT_MEASURED")
    if ceiling:
        print(f"critical-path ceiling:   {ceiling:.2f}x  "
              "(no scheduler can beat the longest dependency chain)")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"parallel_capabilities_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "sequential": seq, "parallel": par,
                   "speedup": speedup, "critical_path_ceiling": ceiling, "rows": rows},
                  f, indent=2, default=str)
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
