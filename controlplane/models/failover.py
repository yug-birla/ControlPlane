"""Try a remote provider for STRONG work, and fall back rather than fail.

WHY THIS EXISTS. ``get_configured_provider`` resolved exactly one
provider: Groq if ``GROQ_API_KEY`` was set, otherwise the local model.
With no key configured that means every request in this deployment --
FAST and STRONG alike -- runs on the local model, which is why the
remote providers were never being used. Gemini was reachable only from
comparison scripts and never from the routing path at all.

WHAT CHANGES, AND WHAT DELIBERATELY DOES NOT. Only the STRONG role gets
a FAILOVER CHAIN. FAST keeps its existing single-provider resolution --
Groq when a key is set, local otherwise -- so with keys configured both
roles are remote (FAST measured at 764 ms on openai/gpt-oss-20b). The
difference is what happens when the first choice is unavailable: STRONG
falls over to Gemini and then to local, FAST does not. STRONG is where
that matters, because its local floor is a 4B on CPU that took 505 s on
the flagship request.

Gemini is placed LAST in the chain on purpose. The project's standing
instruction is "do not use Gemini automatically as the default model",
and it is quota-limited. Being the final fallback for one role is not
being the default; it is being the thing that runs when the preferred
remote provider is absent or failing.

FAILOVER IS AT CALL TIME, NOT ONLY AT CONFIG TIME. A key that is set but
rejected, a rate limit, a timeout -- none of these are visible when the
provider is constructed. Each candidate is tried in order and the chain
records what happened to every one of them, so the dashboard can show
WHICH provider answered and WHY the others did not. A silent fallback
that looked identical to a first-choice success would hide exactly the
thing an operator needs to see.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from controlplane.logging_config import get_logger
from controlplane.models.provider import ModelProvider, ModelProviderError, ModelResult

logger = get_logger("controlplane.models.failover")


@dataclass
class Attempt:
    provider: str
    outcome: str
    """``USED`` | ``UNAVAILABLE`` (not configured) | ``FAILED`` (tried, errored)."""
    detail: str | None = None

    def to_dict(self) -> dict:
        return {"provider": self.provider, "outcome": self.outcome, "detail": self.detail}


@dataclass
class Candidate:
    name: str
    build: object
    """Zero-arg callable returning a ModelProvider. Construction is
    deferred so a missing key is an UNAVAILABLE candidate rather than an
    exception while assembling the chain."""


@dataclass
class FailoverProvider(ModelProvider):
    """Tries each candidate in order; records every outcome."""

    candidates: list[Candidate]
    role: str = "STRONG"
    name: str = "failover"
    attempts: list[Attempt] = field(default_factory=list)
    resolved_name: str | None = None

    def generate(self, *, prompt: str) -> ModelResult:
        self.attempts = []
        errors: list[str] = []

        for candidate in self.candidates:
            try:
                provider = candidate.build()
            except Exception as exc:
                # Not configured, or configured wrongly. Not a failure of
                # the request -- just a candidate that cannot be used.
                self.attempts.append(Attempt(candidate.name, "UNAVAILABLE", str(exc)[:200]))
                continue

            try:
                result = provider.generate(prompt=prompt)
            except ModelProviderError as exc:
                self.attempts.append(Attempt(candidate.name, "FAILED", f"{type(exc).__name__}: {exc}"[:200]))
                errors.append(f"{candidate.name}: {exc}")
                logger.warning(
                    "model_provider_failed_over",
                    extra={"cp_fields": {"provider": candidate.name, "role": self.role,
                                         "error": str(exc)[:200]}},
                )
                continue

            self.attempts.append(Attempt(candidate.name, "USED"))
            self.resolved_name = candidate.name
            if len(self.attempts) > 1:
                logger.info(
                    "model_provider_fallback_used",
                    extra={"cp_fields": {"role": self.role, "used": candidate.name,
                                         "skipped": [a.to_dict() for a in self.attempts[:-1]]}},
                )
            return result

        raise ModelProviderError(
            f"every provider for role={self.role} was unavailable or failed: "
            + ("; ".join(errors) if errors else "none configured")
        )

    def selection_to_dict(self) -> dict:
        """What the dashboard shows: which provider answered, and what
        happened to the ones ahead of it."""
        return {
            "role": self.role,
            "resolved_provider": self.resolved_name,
            "attempts": [a.to_dict() for a in self.attempts],
            "chain": [c.name for c in self.candidates],
        }


def build_strong_chain(settings) -> list[Candidate]:
    """Preferred order for STRONG: Groq, then Gemini, then local.

    Remote first because the local STRONG model is a 4B running on CPU;
    local last because it is the only one that always works offline and
    must never be removed as the floor.
    """
    from controlplane.models.registry import (
        get_gemini_provider,
        resolve_model_name,
    )

    def _groq():
        from controlplane.models.groq_provider import GroqProvider
        from controlplane.errors import ConfigurationError

        if not settings.groq_api_key:
            raise ConfigurationError("GROQ_API_KEY is not set")
        model = resolve_model_name(settings, "STRONG")
        if not model:
            raise ConfigurationError("no Groq model configured for STRONG")
        return GroqProvider(api_key=settings.groq_api_key, model=model)

    def _gemini():
        return get_gemini_provider(settings)

    def _local():
        from controlplane.models.local_generation_provider import (
            get_local_generation_provider,
        )

        return get_local_generation_provider("STRONG")

    return [
        Candidate("groq", _groq),
        Candidate("gemini", _gemini),
        Candidate("local_hf_generation", _local),
    ]
