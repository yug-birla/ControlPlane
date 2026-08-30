"""Dashboard routes -- read-only. Mounted into controlplane.main.app.

Two views per page (bootstrap SS32-36): a server-rendered HTML page for
humans, and a JSON endpoint carrying the same data for programmatic
access / the "dashboard shows..." checklist items. Neither ever accepts
a write -- this package cannot mutate ControlPlane state.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from controlplane.dashboard.agents import (
    MIN_OBSERVATIONS_FOR_ROLE_VERDICT,
    build_agent_view,
)
from controlplane.dashboard.console import build_console
from controlplane.dashboard.live import EXAMPLE_QUERIES, get_run, recent_runs, start_run
from controlplane.dashboard.dataset_health import build_dataset_health
from controlplane.dashboard.evidence import build_evidence
from controlplane.dashboard.queries import (
    aggregate_component_health,
    aggregate_stats,
    build_agent_panel,
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
        request, "detail.html",
        {"detail": detail, "execution_map": execution_map,
         "agent_panel": build_agent_panel(detail)},
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


@router.get("/api/component-health")
def api_component_health() -> dict:
    """System-wide component health: which component is failing across
    requests, as distinct from the per-request diagnostics panel."""
    return aggregate_component_health()


@router.get("/api/evidence")
def api_evidence() -> dict:
    """Baseline vs ControlPlane, ablations, and component experiments --
    read straight from committed experiment result files (§59)."""
    return build_evidence()


@router.get("/evidence", response_class=HTMLResponse)
def dashboard_evidence(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(request, "evidence.html", {"evidence": build_evidence()})


@router.get("/api/datasets")
def api_datasets() -> dict:
    """Dataset inventory with split/label/provenance counted from the
    files themselves (§58)."""
    return build_dataset_health()


@router.get("/datasets", response_class=HTMLResponse)
def dashboard_datasets(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(request, "datasets.html", {"health": build_dataset_health()})


@router.get("/health-map", response_class=HTMLResponse)
def dashboard_component_health(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(
        request, "health.html", {"health": aggregate_component_health()}
    )


@router.get("/api/agents")
def api_agents() -> dict:
    return build_agent_view()


@router.get("/agents", response_class=HTMLResponse)
def dashboard_agents(request: Request) -> HTMLResponse:
    """§50: the dedicated multi-agent control view.

    Answers "which agents were worth running", which agent counts and
    message counts cannot.
    """
    return _templates.TemplateResponse(
        request, "agents.html",
        {"view": build_agent_view(), "min_observations": MIN_OBSERVATIONS_FOR_ROLE_VERDICT},
    )


@router.get("/console/{request_id}", response_class=HTMLResponse)
def dashboard_console(request: Request, request_id: str) -> HTMLResponse:
    """The Live Execution Console: one request as a governed trajectory.

    Reuses ``get_request_detail`` rather than querying again, so the
    console and the detail page can never disagree about what happened.
    """
    detail = get_request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="request not found")
    return _templates.TemplateResponse(
        request, "console.html",
        {"console": build_console(detail), "agent_panel": build_agent_panel(detail)},
    )


@router.get("/api/console/{request_id}")
def api_console(request_id: str) -> dict:
    detail = get_request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="request not found")
    return build_console(detail)


@router.get("/live", response_class=HTMLResponse)
def dashboard_live(request: Request) -> HTMLResponse:
    """Submit a query and watch the real runtime execute it."""
    return _templates.TemplateResponse(
        request, "live.html",
        {"examples": EXAMPLE_QUERIES, "prefill": "", "recent": recent_runs()},
    )


@router.post("/api/run")
def api_run(payload: dict = Body(...)) -> dict:
    """Start a real run on a worker thread and return immediately.

    Calls the SAME ``Runtime.handle`` the API uses -- there is one
    control loop and this is not a second copy of it.
    """
    query = (payload or {}).get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    from controlplane.api.routes import _runtime

    try:
        handle = start_run(query, _runtime)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return handle.to_dict()


@router.get("/api/live/{run_id}")
def api_live(run_id: str) -> dict:
    """Current state of a run, read back from what the runtime has
    already committed. Returns partial state while it is still going."""
    handle = get_run(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run not found")

    console: dict = {"available": False}
    if handle.request_id:
        detail = get_request_detail(handle.request_id)
        if detail:
            console = build_console(detail)
            console["graph"] = build_execution_map(detail)
    return {"run": handle.to_dict(), "console": console}
