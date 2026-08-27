"""Liveness/readiness.

docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS20
distinguishes process-alive / service-ready / capability-usable.
Readiness now checks Postgres connectivity (wired up this milestone);
Redis/Qdrant remain unused placeholders (Layer 3+/11+).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from controlplane.config import get_settings
from controlplane.db.engine import get_engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict:
    return {"status": "alive"}


@router.get("/ready")
def readiness() -> dict:
    settings = get_settings()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_check = "ok"
    except Exception:
        db_check = "unreachable"

    return {
        "status": "ready" if db_check == "ok" else "degraded",
        "application_name": settings.application_name,
        "application_env": settings.application_env,
        "checks": {
            "configuration": "ok",
            "database": db_check,
            "cache": "not_wired (Layer 3+)",
            "vector_store": "not_wired (Layer 11+)",
        },
    }
