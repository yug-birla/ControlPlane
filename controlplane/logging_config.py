"""Structured logging.

Every log record automatically carries request_id/trace_id/trajectory_id
(from controlplane.context) plus timestamp/component/severity/message, per
docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS25. This is
plain stdlib logging -- no event bus. The event bus is a later layer
(FUTURE_WORK.md Layer 3) and must not be anticipated here.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from controlplane.context import current_request_id, current_trace_id, current_trajectory_id

_CONFIGURED = False


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
            "request_id": current_request_id(),
            "trace_id": current_trace_id(),
            "trajectory_id": current_trajectory_id(),
        }
        extra = getattr(record, "cp_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
