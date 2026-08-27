"""ExecutionState -- the foundation of the typed execution context.

Field set is deliberately the Layer 1 minimum from the implementation
bootstrap, not the full state described in
docs/architecture/RUNTIME_FLOW.md SS8 (query_profile, risk_state,
confidence_state, evidence, models_used, ... -- all later layers).
``metadata`` is the extension point until those fields earn their own
place here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from controlplane.context import RequestContext


class ExecutionStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExecutionState(BaseModel):
    request_id: str
    trace_id: str
    trajectory_id: str

    query: str

    current_status: ExecutionStatus
    current_step: str

    plan_id: str | None = None
    plan_version: int | None = None

    created_at: datetime
    updated_at: datetime

    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @staticmethod
    def initial(ctx: RequestContext, query: str) -> "ExecutionState":
        now = datetime.now(timezone.utc)
        return ExecutionState(
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            trajectory_id=ctx.trajectory_id,
            query=query,
            current_status=ExecutionStatus.RECEIVED,
            current_step="received",
            created_at=now,
            updated_at=now,
        )

    def advance(self, step: str, status: ExecutionStatus | None = None) -> "ExecutionState":
        self.current_step = step
        if status is not None:
            self.current_status = status
        self.updated_at = datetime.now(timezone.utc)
        return self

    def fail(self, step: str, error_message: str) -> "ExecutionState":
        self.errors.append(error_message)
        return self.advance(step, ExecutionStatus.FAILED)
