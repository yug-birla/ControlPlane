"""Dashboard routes -- read-only. Mounted into controlplane.main.app.

Two views per page (bootstrap SS32-36): a server-rendered HTML page for
humans, and a JSON endpoint carrying the same data for programmatic
access / the "dashboard shows..." checklist items. Neither ever accepts
a write -- this package cannot mutate ControlPlane state.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from controlplane.dashboard.queries import (
    aggregate_stats,
    build_execution_map,
    get_request_detail,
    list_recent_requests,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("", response_class=HTMLResponse)
def dashboard_home(request: Request) -> HTMLResponse:
    requests_ = list_recent_requests()
    stats = aggregate_stats()
    return _templates.TemplateResponse(request, "list.html", {"requests": requests_, "stats": stats})


@router.get("/requests/{request_id}", response_class=HTMLResponse)
def dashboard_request_detail(request: Request, request_id: str) -> HTMLResponse:
    detail = get_request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="request not found")
    # Derived from the detail dict already fetched -- no extra queries, so
    # drawing the map costs the request nothing.
    execution_map = build_execution_map(detail)
    return _templates.TemplateResponse(
        request, "detail.html", {"detail": detail, "execution_map": execution_map}
    )


@router.get("/api/requests")
def api_list_requests() -> list[dict]:
    return list_recent_requests()


@router.get("/api/requests/{request_id}")
def api_request_detail(request_id: str) -> dict:
    detail = get_request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="request not found")
    return detail


@router.get("/api/stats")
def api_stats() -> dict:
    return aggregate_stats()
