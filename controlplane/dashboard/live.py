"""Submit a query and watch the real runtime execute it.

WHY A SECOND SUBMIT PATH. ``POST /v1/requests`` is synchronous: it
returns when the whole control loop has finished, which on this hardware
is 19 s for a fast path and ~9 min when the router escalates to the 4B
model. That is the correct contract for an API client and useless for
watching an execution unfold.

This runs the SAME ``Runtime.handle`` on a worker thread and returns the
request id immediately, so the page can follow progress. It is not a
second pipeline and not a simulation -- there is exactly one
implementation of the control loop and this calls it.

HOW "LIVE" IS ACHIEVED WITHOUT A NEW TRANSPORT. Every stage of the
runtime publishes its event through ``_publish``, which commits inside
its own session as it happens. The events are therefore already in the
database while the request is still running, and the page reads them
back by polling -- the transport the dashboard already uses. No
WebSocket, no SSE, no second event infrastructure.

WHAT THIS MEANS FOR HONESTY. Progress shown is progress that actually
occurred: a stage lights up because its event is committed, not because
a timer advanced. A request that hangs shows a spine that stops
advancing, which is the truth about it.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Bounded: this is a demo/console affordance, not a job queue. Refusing
# beyond the cap is honest about what it is; silently queueing would
# invite the impression of an execution backend that does not exist.
MAX_CONCURRENT_RUNS = 2


@dataclass
class RunHandle:
    run_id: str
    request_id: str | None = None
    trace_id: str | None = None
    trajectory_id: str | None = None
    query: str = ""
    status: str = "STARTING"
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        elapsed = ((self.finished_at or datetime.now(timezone.utc)) - self.started_at)
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "trajectory_id": self.trajectory_id,
            "query": self.query,
            "status": self.status,
            "error": self.error,
            "elapsed_ms": int(elapsed.total_seconds() * 1000),
            "finished": self.finished_at is not None,
        }


_runs: dict[str, RunHandle] = {}
_lock = threading.Lock()


def active_run_count() -> int:
    with _lock:
        return sum(1 for r in _runs.values() if r.finished_at is None)


def get_run(run_id: str) -> RunHandle | None:
    with _lock:
        return _runs.get(run_id)


def recent_runs(limit: int = 10) -> list[dict]:
    with _lock:
        runs = sorted(_runs.values(), key=lambda r: r.started_at, reverse=True)
    return [r.to_dict() for r in runs[:limit]]


def start_run(query: str, runtime) -> RunHandle:
    """Execute ``query`` on a worker thread against the real runtime."""
    if active_run_count() >= MAX_CONCURRENT_RUNS:
        raise RuntimeError(
            f"{MAX_CONCURRENT_RUNS} runs already in flight -- this console executes real "
            "requests against local models and will not queue more"
        )

    handle = RunHandle(run_id=f"run_{uuid.uuid4().hex[:12]}", query=query)
    with _lock:
        _runs[handle.run_id] = handle

    def _execute() -> None:
        from controlplane.context import RequestContext
        from controlplane.state import ExecutionState

        ctx = RequestContext.new()
        # Published before execution so the page can start following the
        # trajectory immediately rather than after the first stage.
        handle.request_id = ctx.request_id
        handle.trace_id = ctx.trace_id
        handle.trajectory_id = ctx.trajectory_id
        handle.status = "RUNNING"
        try:
            with ctx.bind():
                state = ExecutionState.initial(ctx=ctx, query=query)
                runtime.handle(ctx, state)
            handle.status = "COMPLETED"
        except Exception as exc:  # a failed run is a REPORTED outcome
            handle.status = "FAILED"
            # Type and message only. The failure is surfaced in the UI
            # from the recorded trajectory and failure localization; this
            # is the fallback for a failure that never got that far.
            handle.error = f"{type(exc).__name__}: {exc}"
        finally:
            handle.finished_at = datetime.now(timezone.utc)

    threading.Thread(target=_execute, name=f"cp-run-{handle.run_id}", daemon=True).start()
    return handle


EXAMPLE_QUERIES = [
    ("Fast path",
     "What is the capital of France?",
     "Low complexity, no enterprise source, no action -- expect the FAST model, no agents."),
    ("Retrieval",
     "What is our meal reimbursement limit for domestic travel?",
     "One document source -- expect RAG through MCP and a plain capability path."),
    ("Multi-agent, parallel",
     "Look up our Q4 revenue in the database and the travel policy document, "
     "then send a summary notification to finance.",
     "Two independent sources plus an action -- expect parallel gatherer agents, a "
     "confidential handoff, and HUMAN_REVIEW on the send. SLOW: the router escalates "
     "to the 4B model (~9 min)."),
    ("Destructive",
     "Please drop the customers table from the production database.",
     "Expect the destructive-operation hard constraint: BLOCK, never executed."),
]
