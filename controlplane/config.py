"""Configuration foundation.

Single place configuration is read from the environment. Nothing else in
the codebase should call ``os.environ`` directly -- see
docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS9.

Connection placeholders (``database_url``, ``redis_url``, ``qdrant_url``,
``model_provider_keys``, ``mcp_endpoints``) are read but intentionally
unused in Layer 1 -- no code connects to them yet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    application_name: str = "controlplane"
    application_env: str = "development"
    log_level: str = "INFO"

    # Infrastructure placeholders (Layer 1 does not connect to any of these).
    database_url: str | None = None
    redis_url: str | None = None
    qdrant_url: str | None = None
    model_provider_keys: str | None = None
    mcp_endpoints: str | None = None

    feature_flags: frozenset[str] = field(default_factory=frozenset)

    @staticmethod
    def from_env() -> "Settings":
        raw_flags = os.environ.get("FEATURE_FLAGS", "")
        flags = frozenset(f.strip() for f in raw_flags.split(",") if f.strip())
        return Settings(
            application_name=os.environ.get("APPLICATION_NAME", "controlplane"),
            application_env=os.environ.get("APPLICATION_ENV", "development"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            database_url=os.environ.get("DATABASE_URL"),
            redis_url=os.environ.get("REDIS_URL"),
            qdrant_url=os.environ.get("QDRANT_URL"),
            model_provider_keys=os.environ.get("MODEL_PROVIDER_KEYS"),
            mcp_endpoints=os.environ.get("MCP_ENDPOINTS"),
            feature_flags=flags,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
