"""Traceable runtime -- Layer 1 only.

Deliberately deterministic: it echoes the query back with no query
profiling, routing, retrieval, or model call. Every future capability
(Query Intelligence, Capability Router, Model Router, RAG, ...) plugs in
here later, behind this same ExecutionState-in/ExecutionState-out shape,
without changing the API layer. See docs/PROJECT_STATE/FUTURE_WORK.md.
"""

from __future__ import annotations

from controlplane.logging_config import get_logger
from controlplane.state import ExecutionState, ExecutionStatus

logger = get_logger("controlplane.runtime")


class Runtime:
    """Layer 1 runtime: advances ExecutionState through a fixed, mocked path."""

    def handle(self, state: ExecutionState) -> ExecutionState:
        state.advance("processing", ExecutionStatus.PROCESSING)
        logger.info("execution_step", extra={"cp_fields": {"step": state.current_step}})

        answer = (
            f"Layer 1 foundation received: {state.query!r}. "
            "No query intelligence, routing, retrieval, or model call is implemented yet."
        )
        state.metadata["answer"] = answer

        state.advance("completed", ExecutionStatus.COMPLETED)
        logger.info("execution_step", extra={"cp_fields": {"step": state.current_step}})
        return state
