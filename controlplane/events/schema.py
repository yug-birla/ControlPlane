"""Canonical event contract -- docs/architecture/EVENT_MODEL.md.

Only the four events this milestone's flow actually produces are defined
here (a subset of EVENT_MODEL.md SS14's ~29-event canonical taxonomy).
Later layers add more members to ``EventType`` as they start emitting
them -- do not pre-declare events nothing produces yet.

Event vs. Command vs. State Update (EVENT_MODEL.md SS3): this module only
carries events ("what happened"). It must never encode a policy decision
("what should happen next") -- see controlplane/runtime.py, which is the
only place that interprets an event and decides.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class EventType(str, Enum):
    QUERY_RECEIVED = "QUERY_RECEIVED"
    QUERY_PROFILED = "QUERY_PROFILED"
    """docs/architecture/RUNTIME_FLOW.md SS14 canonical event list -- first
    implemented this milestone (Query Profiler now exists to emit it)."""
    RISK_DETECTED = "RISK_DETECTED"
    """docs/architecture/RUNTIME_FLOW.md SS14 -- emitted for every query
    (not only risky ones), analogous to QUERY_PROFILED; the ``severity``
    field is what actually varies with the assessed risk."""
    PLAN_CREATED = "PLAN_CREATED"
    """docs/architecture/EVENT_MODEL.md SS14/15.3 -- emitted once the
    Capability Router + Model Router have produced the Execution Graph
    and model-role decision for this request (Milestone 3)."""
    ROUTE_STARTED = "ROUTE_STARTED"
    ROUTE_COMPLETED = "ROUTE_COMPLETED"
    """docs/architecture/EVENT_MODEL.md SS15.5/15.6 -- one pair per
    Execution Graph node the ``GraphExecutor`` runs."""
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    """docs/architecture/EVENT_MODEL.md SS15.28 -- emitted when the Model
    Router's action is HUMAN_REVIEW (HIGH_RISK/CRITICAL_ACTION policy
    tier) or ABSTAIN (an agentic request whose AGENT capability was
    policy-restricted)."""
    MODEL_CALLED = "MODEL_CALLED"
    MODEL_FAILURE = "MODEL_FAILURE"
    FINAL_RESPONSE_GENERATED = "FINAL_RESPONSE_GENERATED"


class Severity(str, Enum):
    """docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md SS64.3:
    canonical for the event *transport* layer (narrower than the S0-S4
    governance severity scale in FAILURE_AND_RECOVERY.md)."""

    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


_DEFAULT_SEVERITY = {
    EventType.QUERY_RECEIVED: Severity.INFO,
    EventType.QUERY_PROFILED: Severity.INFO,
    EventType.RISK_DETECTED: Severity.INFO,  # overridden per-call with the assessed severity -- see controlplane/runtime.py
    EventType.PLAN_CREATED: Severity.INFO,
    EventType.ROUTE_STARTED: Severity.INFO,
    EventType.ROUTE_COMPLETED: Severity.INFO,
    EventType.HUMAN_REVIEW_REQUIRED: Severity.HIGH,
    EventType.MODEL_CALLED: Severity.INFO,
    EventType.MODEL_FAILURE: Severity.HIGH,
    EventType.FINAL_RESPONSE_GENERATED: Severity.INFO,
}


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4()}")
    event_type: EventType
    event_version: str = "1"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    severity: Severity
    request_id: str
    trace_id: str
    trajectory_id: str
    correlation_id: str | None = None
    payload: dict = Field(default_factory=dict)

    @staticmethod
    def create(
        event_type: EventType,
        *,
        source: str,
        request_id: str,
        trace_id: str,
        trajectory_id: str,
        payload: dict | None = None,
        severity: Severity | None = None,
    ) -> "Event":
        return Event(
            event_type=event_type,
            source=source,
            severity=severity or _DEFAULT_SEVERITY[event_type],
            request_id=request_id,
            trace_id=trace_id,
            trajectory_id=trajectory_id,
            correlation_id=trace_id,
            payload=payload or {},
        )
