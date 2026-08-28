"""Application entrypoint. Run with: uvicorn controlplane.main:app"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from controlplane.api.health import router as health_router
from controlplane.api.routes import router as requests_router
from controlplane.config import get_settings
from controlplane.dashboard.router import router as dashboard_router
from controlplane.errors import ControlPlaneError, InternalError
from controlplane.logging_config import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("controlplane.main")

app = FastAPI(title="ControlPlane.ai", version="0.3.0")
app.include_router(health_router)
app.include_router(requests_router)
app.include_router(dashboard_router)


def _error_response(error: ControlPlaneError) -> JSONResponse:
    body = error.to_dict()
    body["request_id"] = error.request_id
    body["trace_id"] = error.trace_id
    return JSONResponse(status_code=error.http_status, content=body)


@app.exception_handler(ControlPlaneError)
def handle_controlplane_error(request: Request, exc: ControlPlaneError) -> JSONResponse:
    logger.warning("request_failed", extra={"cp_fields": {"error_code": exc.error_code}})
    return _error_response(exc)


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    from controlplane.errors import ValidationError

    logger.warning("request_validation_failed")
    return _error_response(ValidationError(str(exc.errors())))


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception")
    return _error_response(InternalError("an internal error occurred"))
