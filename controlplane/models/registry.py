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
from controlplane.models.gemini_provider import GeminiProvider
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
    """Resolve a provider for ``role``.

    Precedence (Milestone 9):
      1. ``CONTROLPLANE_LOCAL_GENERATION=1`` -> the offline local model,
         even if a Groq key is present (lets an experiment pin the
         reproducible local model deliberately).
      2. ``GROQ_API_KEY`` set -> Groq (the normal interactive path).
      3. Neither -> the offline local model, if its weights are cached.

    Step 3 is why this no longer raises when no API key exists: through
    Milestone 8 a key-less environment had NO generative model at all, so
    the entire system was unrunnable end-to-end offline and every
    scenario fell back to scripted fakes. See
    ``controlplane.models.local_generation_provider`` for the full
    finding.
    """
    if settings.use_local_generation or not settings.groq_api_key:
        from controlplane.models.local_generation_provider import (
            get_local_generation_provider,
        )
        from controlplane.models.provider import ModelProviderError

        try:
            return get_local_generation_provider(role)
        except ModelProviderError as exc:
            raise ConfigurationError(
                "no remote model provider is configured (GROQ_API_KEY unset) and the "
                f"local fallback model is unavailable: {exc}"
            ) from exc

    model = resolve_model_name(settings, role)
    if not model:
        raise ConfigurationError(
            f"no model configured for role={role!r} (GROQ_MODEL_{role} / GROQ_MODEL are all unset) "
            "-- the model name is never hard-coded, see docs/PROJECT_STATE/DECISIONS.md"
        )
    return GroqProvider(api_key=settings.groq_api_key, model=model)


def get_gemini_provider(settings: Settings) -> ModelProvider:
    """A separate, conservatively-used comparison provider -- never called
    from ``controlplane.routing.model_router``'s FAST/STRONG path. Used
    only by explicit comparison/benchmark scripts in
    ``controlplane/experiments/`` (bootstrap instruction: "Do NOT use
    Gemini automatically as the default model")."""
    keys = [k for k in (settings.gemini_api_key_1, settings.gemini_api_key_2) if k]
    if not keys:
        raise ConfigurationError("neither GEMINI_API_KEY_1 nor GEMINI_API_KEY_2 is set")
    if not settings.gemini_model:
        raise ConfigurationError(
            "GEMINI_MODEL is not set -- the model name is never hard-coded, see docs/PROJECT_STATE/DECISIONS.md"
        )
    return GeminiProvider(api_keys=keys, model=settings.gemini_model)
