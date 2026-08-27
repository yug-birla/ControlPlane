"""Resolves the one configured ModelProvider.

Not a Model Capability Registry (that's Layer 10 -- model metadata,
capability profiles, multiple registered models). This milestone uses
exactly one explicitly configured provider/model; there is no routing.
"""

from __future__ import annotations

from controlplane.config import Settings
from controlplane.errors import ConfigurationError
from controlplane.models.groq_provider import GroqProvider
from controlplane.models.provider import ModelProvider


def get_configured_provider(settings: Settings) -> ModelProvider:
    if not settings.groq_api_key:
        raise ConfigurationError(
            "GROQ_API_KEY is not set; no model provider is configured"
        )
    if not settings.groq_model:
        raise ConfigurationError(
            "GROQ_MODEL is not set; no model provider is configured "
            "(the model name is never hard-coded -- see docs/PROJECT_STATE/DECISIONS.md)"
        )
    return GroqProvider(api_key=settings.groq_api_key, model=settings.groq_model)
