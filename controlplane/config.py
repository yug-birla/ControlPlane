"""Configuration foundation.

Single place configuration is read from the environment. Nothing else in
the codebase should call ``os.environ`` directly -- see
docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS9.

``redis_url``, ``qdrant_url``, ``mcp_endpoints`` remain unused placeholders
(Layer 3+/5+/11+). ``database_url`` is used from Milestone 1 onward.
``groq_api_key`` is read from the environment only -- never given a
fallback value here and never logged. See docs/PROJECT_STATE/DECISIONS.md
for why no model name is hard-coded as a default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://controlplane:controlplane_dev_password@localhost:5433/controlplane"
)


@dataclass(frozen=True)
class Settings:
    application_name: str = "controlplane"
    application_env: str = "development"
    log_level: str = "INFO"

    database_url: str = _DEFAULT_DATABASE_URL

    # Infrastructure placeholders -- not used until later layers.
    redis_url: str | None = None
    qdrant_url: str | None = None
    mcp_endpoints: str | None = None

    # Model provider configuration. groq_api_key is a secret: read from the
    # environment only, never defaulted, never logged, never persisted.
    groq_api_key: str | None = None
    groq_model: str | None = None
    # Milestone 3: Model Router FAST/STRONG roles. Each falls back to
    # groq_model when its own env var is unset, so a single-model
    # deployment (Milestone 1/2's setup) keeps working unchanged -- see
    # docs/PROJECT_STATE/DECISIONS.md for why role-specific model names
    # are still never hard-coded here.
    groq_model_fast: str | None = None
    groq_model_strong: str | None = None

    # Gemini: comparison-only provider (never the default route -- quota is
    # limited/non-free). Two keys supported for quota headroom; both are
    # secrets, read from the environment only, never defaulted/logged.
    gemini_api_key_1: str | None = None
    gemini_api_key_2: str | None = None
    gemini_model: str | None = None

    # Milestone 9: force the offline local generative model even when a
    # Groq key is present. Not a secret. Used by experiments that need a
    # reproducible, key-independent model; also the automatic fallback
    # when no remote key is configured (see controlplane.models.registry).
    use_local_generation: bool = False

    feature_flags: frozenset[str] = field(default_factory=frozenset)

    @staticmethod
    def from_env() -> "Settings":
        # Load a local .env if one exists, WITHOUT overriding anything the
        # process was already started with -- an explicitly exported
        # variable must always win over a file on disk, or a deliberately
        # pinned experiment configuration would be silently overwritten.
        #
        # Secrets are read from the environment only and are never given a
        # default here; .env is gitignored and is not part of the
        # repository.
        _load_dotenv_once()

        raw_flags = os.environ.get("FEATURE_FLAGS", "")
        flags = frozenset(f.strip() for f in raw_flags.split(",") if f.strip())
        return Settings(
            application_name=os.environ.get("APPLICATION_NAME", "controlplane"),
            application_env=os.environ.get("APPLICATION_ENV", "development"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
            redis_url=os.environ.get("REDIS_URL"),
            qdrant_url=os.environ.get("QDRANT_URL"),
            mcp_endpoints=os.environ.get("MCP_ENDPOINTS"),
            groq_api_key=os.environ.get("GROQ_API_KEY"),
            groq_model=os.environ.get("GROQ_MODEL"),
            groq_model_fast=os.environ.get("GROQ_MODEL_FAST"),
            groq_model_strong=os.environ.get("GROQ_MODEL_STRONG"),
            gemini_api_key_1=os.environ.get("GEMINI_API_KEY_1"),
            gemini_api_key_2=os.environ.get("GEMINI_API_KEY_2"),
            gemini_model=os.environ.get("GEMINI_MODEL"),
            use_local_generation=os.environ.get("CONTROLPLANE_LOCAL_GENERATION", "") == "1",
            feature_flags=flags,
        )


_DOTENV_LOADED = False


def _load_dotenv_once() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    try:
        from pathlib import Path

        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except Exception:
        # A missing or unreadable .env must never stop the application:
        # every value it can supply has an environment fallback already.
        pass


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
