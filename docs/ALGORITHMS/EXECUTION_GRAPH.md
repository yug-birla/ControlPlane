# Execution Graph + Graph Executor

**Status:** IMPLEMENTED (Milestone 3, 2026-08-28)

## Problem

Represent "what should happen" for one request as an explicit dependency graph (`docs/architecture/RUNTIME_FLOW.md` §6.1), and run it respecting dependency order — with independent branches (e.g. SQL + RAG before a merge) able to execute concurrently rather than strictly sequentially.

## Architecture Location

`controlplane/execution/` — `graph.py` (data structure), `executor.py` (runner). Built by `controlplane/routing/capability_router.py`; run by `controlplane/runtime.py::_execute_graph`.

## Design

`ExecutionGraph` is a plain dict of `ExecutionNode`s with `depends_on` tuples — no DB, no event bus, fully unit-testable in isolation (`tests/test_execution_graph.py`). `validate()` checks for unknown dependencies and cycles (DFS three-color algorithm) before any execution. `GraphExecutor.run(graph, mode)` repeatedly computes the "ready wave" (`PENDING` nodes whose dependencies are all `COMPLETED`) and runs it — one node at a time in `mode="sequential"`, via a bounded `ThreadPoolExecutor` (`max_workers=4` default) in `mode="parallel"`. A node whose dependency `FAILED`/`SKIPPED` is marked `BLOCKED`, never silently left `PENDING` forever (bootstrap §31: partial execution must be represented, not hidden).

A capability with no registered handler runs the explicit `mocked_capability_handler`, returning `{"status": "MOCKED", ...}` — never fabricated content (bootstrap §54).

## Candidate Alternatives

- **A dedicated workflow engine (Airflow/Prefect/Temporal)** — rejected per bootstrap §7/§36: 10,000 interactions/week is a planning workload, not a justification for adding a distributed workflow orchestrator's operational overhead to the prototype.
- **`asyncio` instead of threads** — the actual node work this milestone (a Groq HTTP call, or an instant mocked return) is I/O-bound either way; `ThreadPoolExecutor` was chosen for simplicity (no need to make the rest of the codebase async) and because Python's GIL is released during I/O regardless of which concurrency primitive is used.

## Inputs / Outputs

Input: `ExecutionGraph` (nodes + dependency edges) + `handlers: dict[capability, Callable[[ExecutionNode], dict]]`. Output: `GraphResult` (completed/failed/blocked node-id lists, `total_latency_ms`, `critical_path_ms`).

## Dataset

None — this is infrastructure, not a learned/data-dependent component.

## Training / Fine-Tuning Requirement

None.

## Compute / Latency

See `docs/EVALUATION/EXECUTION_GRAPH_RESULTS.md` for the measured sequential-vs-parallel benchmark (simulated per-node latency, since SQL/RAG have no real implementation yet).

## Metrics

Structural correctness (cycle/unknown-dependency detection, `BLOCKED` propagation) verified by `tests/test_execution_graph.py` and `tests/test_graph_executor.py`. Concurrency speedup measured by `controlplane/experiments/benchmark_graph_execution.py`.

## Failure Modes

A node handler exception is caught by the executor (never crashes the process) and recorded as `FAILED` with `node.error = str(exc)`; `controlplane/runtime.py`'s generation handler separately captures the real typed exception object (`ControlPlaneError` subclass) so the API layer still returns the correct structured error code (`DEPENDENCY_ERROR`/`TIMEOUT_ERROR`/`CONFIGURATION_ERROR`) rather than a generic failure.

## Result

Measured ~1.96x speedup running a 2-branch parallel graph vs. sequential (`docs/EVALUATION/EXECUTION_GRAPH_RESULTS.md`) — real, though bounded by the simulated (not real-capability) per-node latency used for the benchmark.

## Final Decision

Adopted as the runtime's execution mechanism for every request (`controlplane/runtime.py::_execute_graph`), replacing Milestone 1/2's single hard-coded model-invocation step.

## Version

v1 — 2026-08-28.
