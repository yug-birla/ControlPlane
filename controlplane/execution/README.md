# controlplane/execution/

**Purpose:** the Execution Graph and Graph Executor — "what should happen" for one request (`docs/architecture/RUNTIME_FLOW.md` §6.1). See `docs/ALGORITHMS/EXECUTION_GRAPH.md`.

## Interface

- `graph.py`: `ExecutionNode`, `NodeStatus`, `ExecutionGraph` (add_node, validate, ready_nodes, blocked_nodes, is_complete, critical_path_ms, to_dict). Pure/dependency-free — no DB, no event bus.
- `executor.py`: `GraphExecutor.run(graph, mode="parallel"|"sequential") -> GraphResult`. Runs nodes wave-by-wave respecting dependencies; a wave's nodes run concurrently (bounded `ThreadPoolExecutor`, default `max_workers=4`) in `"parallel"` mode, one at a time in `"sequential"` mode. `mocked_capability_handler` is the default handler for any capability with no registered real implementation.

## Dependencies

None beyond stdlib (`concurrent.futures`).

## Limitations

- Per-node `ROUTE_STARTED`/`ROUTE_COMPLETED` events (emitted by `controlplane.runtime`) are recorded **after** the whole graph finishes running, not live per-node — the executor itself has no event/trajectory hook, by design (keeps it dependency-free and thread-safety-simple). See `controlplane/runtime.py::_execute_graph`.
- SQL/RAG/WEB/CHAT_HISTORY/MEMORY/AGENT capability nodes always run via `mocked_capability_handler` — no real implementation exists yet (Layer 5/11/18, see `docs/PROJECT_STATE/FUTURE_WORK.md`). Only `"generation"` (a model call) has a real handler, wired in `controlplane/runtime.py`.
- No retry/compensation logic yet — a failed node's downstream dependents are marked `BLOCKED`, not retried.

## Extension points

A real SQL/RAG/AGENT capability just needs a handler function (`ExecutionNode -> dict`) registered in `GraphExecutor(handlers={...})` — no change to `graph.py`, `executor.py`, or `controlplane/routing/` needed.
