"""Request/trace/trajectory identity.

docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS2 requires
every request to carry ``request_id`` and ``trace_id``; the trajectory
contract (docs/architecture/TRAJECTORY_AND_LEDGER.md) requires
``trajectory_id``. Layer 1 only establishes these identifiers and makes
them available to structured logging via contextvars -- the full
Trajectory Store / Execution Ledger subsystem is a later layer.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_trajectory_id: ContextVar[str | None] = ContextVar("trajectory_id", default=None)


def generate_request_id() -> str:
    return f"req_{uuid.uuid4()}"


def generate_trace_id() -> str:
    return f"trace_{uuid.uuid4()}"


def generate_trajectory_id() -> str:
    return f"traj_{uuid.uuid4()}"


@dataclass(frozen=True)
class RequestContext:
    """The identifiers that must remain consistent for one request's lifetime."""

    request_id: str
    trace_id: str
    trajectory_id: str

    @staticmethod
    def new() -> "RequestContext":
        return RequestContext(
            request_id=generate_request_id(),
            trace_id=generate_trace_id(),
            trajectory_id=generate_trajectory_id(),
        )

    @contextmanager
    def bind(self) -> Iterator["RequestContext"]:
        """Make these identifiers visible to structured logging for this request."""
        req_token = _request_id.set(self.request_id)
        trace_token = _trace_id.set(self.trace_id)
        traj_token = _trajectory_id.set(self.trajectory_id)
        try:
            yield self
        finally:
            _request_id.reset(req_token)
            _trace_id.reset(trace_token)
            _trajectory_id.reset(traj_token)


def current_request_id() -> str | None:
    return _request_id.get()


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_trajectory_id() -> str | None:
    return _trajectory_id.get()
