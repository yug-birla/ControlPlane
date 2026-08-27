"""API request/response contracts.

ResponseEnvelope intentionally has no trust/risk/confidence/evaluation
fields -- those subsystems don't exist yet, and the bootstrap explicitly
forbids faking them. ``metadata`` is open-ended so later layers can add
real fields without breaking this contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from controlplane.state import ExecutionState


class RequestIn(BaseModel):
    query: str
    application_id: str | None = None


class ResponseEnvelope(BaseModel):
    request_id: str
    trace_id: str
    trajectory_id: str
    status: str
    answer: str | None = None
    metadata: dict = Field(default_factory=dict)

    @staticmethod
    def from_state(state: ExecutionState) -> "ResponseEnvelope":
        metadata = {k: v for k, v in state.metadata.items() if k != "answer"}
        return ResponseEnvelope(
            request_id=state.request_id,
            trace_id=state.trace_id,
            trajectory_id=state.trajectory_id,
            status=state.current_status.value,
            answer=state.metadata.get("answer"),
            metadata=metadata,
        )


class ErrorEnvelope(BaseModel):
    error_code: str
    message: str
    retryable: bool
    request_id: str | None = None
    trace_id: str | None = None
