"""MCP wire contracts: normalized invocation results and failure taxonomy.

Every capability reached through the fabric returns the SAME shape,
whatever the underlying implementation is. That is the entire point of a
capability fabric: the planner and executor should not need to know
whether evidence came from a local RAG implementation or a remote MCP
server.

Deliberately NOT here: anything that decides. No risk scoring, no policy,
no retry strategy, no routing. A failure is *classified* here so
ControlPlane can decide what to do about it; the deciding happens in the
Decision Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MCPStatus(str, Enum):
    OK = "OK"
    FAILED = "FAILED"


class MCPFailure(str, Enum):
    """The failure taxonomy the architecture requires.

    Classified, not handled: each maps to a different sensible control
    response (retry vs. alternate capability vs. escalate), but choosing
    among those is ControlPlane's job.
    """

    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CAPABILITY_NOT_FOUND = "CAPABILITY_NOT_FOUND"
    SERVER_FAILURE = "SERVER_FAILURE"


# Which failures could plausibly succeed on a retry of the SAME
# capability, and which are pointless to retry. Encoded as data so the
# control loop can consult it, rather than as a retry loop here -- a
# fabric that retries on its own has started making control decisions.
_RETRYABLE = {MCPFailure.TIMEOUT, MCPFailure.SERVER_FAILURE, MCPFailure.UNAVAILABLE}


def is_retryable(failure: MCPFailure) -> bool:
    return failure in _RETRYABLE


@dataclass
class MCPResult:
    """Normalized result of one capability invocation."""

    capability_id: str
    operation_id: str
    status: MCPStatus
    server: str
    output: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    latency_ms: int = 0
    failure: MCPFailure | None = None
    error: str | None = None
    permissions_used: frozenset[str] = field(default_factory=frozenset)
    provenance: str = "MCP"

    @property
    def ok(self) -> bool:
        return self.status is MCPStatus.OK

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "operation_id": self.operation_id,
            "status": self.status.value,
            "server": self.server,
            "output": self.output,
            "evidence_count": len(self.evidence),
            "latency_ms": self.latency_ms,
            "failure": self.failure.value if self.failure else None,
            "error": self.error,
            "permissions_used": sorted(self.permissions_used),
            "provenance": self.provenance,
        }
