"""Resolves the configured ModelProvider for a given Model Router role.

Not a Model Capability Registry (that's ``model_registry`` the Postgres
table + ``registry_seed.py`` -- model metadata, capability profiles,
multiple registered models). This resolves an actual callable provider
instance for FAST or STRONG; there is still exactly one real provider
(Groq) behind both roles -- see docs/PROJECT_STATE/DECISIONS.md for why
a local generative model pool (the Qwen3 tier from
docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md) was deferred out of
this milestone rather than half-built.
"""

from __future__ import annotations

from controlplane.config import Settings
from controlplane.errors import ConfigurationError
from controlplane.models.groq_provider import GroqProvider
from controlplane.models.provider import ModelProvider

_ROLE_MODEL_FIELD = {
    "FAST": "groq_model_fast",
    "STRONG": "groq_model_strong",
}


def resolve_model_name(settings: Settings, role: str = "STRONG") -> str | None:
    """The model name for ``role``, falling back to ``groq_model`` when no
    role-specific override is configured (keeps a single-model deployment
    working unchanged)."""
    field = _ROLE_MODEL_FIELD.get(role)
    role_specific = getattr(settings, field, None) if field else None
    return role_specific or settings.groq_model


def get_configured_provider(settings: Settings, role: str = "STRONG") -> ModelProvider:
    if not settings.groq_api_key:
        raise ConfigurationError(
            "GROQ_API_KEY is not set; no model provider is configured"
        )
    model = resolve_model_name(settings, role)
    if not model:
        raise ConfigurationError(
            f"no model configured for role={role!r} (GROQ_MODEL_{role} / GROQ_MODEL are all unset) "
            "-- the model name is never hard-coded, see docs/PROJECT_STATE/DECISIONS.md"
        )
    return GroqProvider(api_key=settings.groq_api_key, model=model)
