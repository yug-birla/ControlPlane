"""Liveness/readiness -- lightweight by design (no model or DB calls).

docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS20
distinguishes process-alive / service-ready / capability-usable. Layer 1
has no real dependencies wired up yet (DATABASE_URL etc. are unused
placeholders -- see controlplane/config.py), so readiness only confirms
configuration loaded, not that Postgres/Redis/Qdrant are reachable.
"""

from __future__ import annotations

from fastapi import APIRouter

from controlplane.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict:
    return {"status": "alive"}


@router.get("/ready")
def readiness() -> dict:
    settings = get_settings()
    return {
        "status": "ready",
        "application_name": settings.application_name,
        "application_env": settings.application_env,
        "checks": {
            "configuration": "ok",
            "database": "not_wired (Layer 2+)",
            "cache": "not_wired (Layer 2+)",
            "vector_store": "not_wired (Layer 11+)",
        },
    }
