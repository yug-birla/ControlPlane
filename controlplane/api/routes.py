"""API entry point.

Per the Layer 1 spec: receive request -> validate input -> generate
identifiers -> create execution context -> invoke the runtime -> return a
structured response. No routing/business logic belongs in this module --
that is what controlplane.runtime.Runtime exists to own, and later layers
extend the runtime, not this file.
"""

from __future__ import annotations

from fastapi import APIRouter

from controlplane.context import RequestContext
from controlplane.errors import ValidationError
from controlplane.logging_config import get_logger
from controlplane.runtime import Runtime
from controlplane.schemas import RequestIn, ResponseEnvelope
from controlplane.state import ExecutionState

router = APIRouter(prefix="/v1", tags=["requests"])
logger = get_logger("controlplane.api")
_runtime = Runtime()


@router.post("/requests", response_model=ResponseEnvelope)
def create_request(payload: RequestIn) -> ResponseEnvelope:
    query = payload.query.strip()
    if not query:
        raise ValidationError("query must not be empty")

    ctx = RequestContext.new()
    with ctx.bind():
        logger.info("request_received")
        state = ExecutionState.initial(ctx=ctx, query=query)
        state = _runtime.handle(state)
        logger.info("request_completed")

    return ResponseEnvelope.from_state(state)
