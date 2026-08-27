"""Groq adapter -- the only module in ControlPlane allowed to import the
``groq`` SDK. Everything else uses controlplane.models.provider.ModelProvider.

SECURITY: the API key is passed in by the caller (read from
controlplane.config.Settings.groq_api_key, which reads GROQ_API_KEY from
the environment). This module never logs, stores, or echoes it.
"""

from __future__ import annotations

import time

import groq

from controlplane.models.provider import (
    ModelProvider,
    ModelProviderError,
    ModelProviderTimeout,
    ModelResult,
)


class GroqProvider(ModelProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ModelProviderError("GROQ_API_KEY is not configured")
        if not model:
            raise ModelProviderError("GROQ_MODEL is not configured")
        self._client = groq.Groq(api_key=api_key, timeout=timeout)
        self._model = model

    def generate(self, *, prompt: str) -> ModelResult:
        start = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
        except groq.APITimeoutError as exc:
            raise ModelProviderTimeout(str(exc)) from exc
        except groq.GroqError as exc:
            raise ModelProviderError(str(exc)) from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        choice = response.choices[0]
        usage = response.usage
        return ModelResult(
            provider=self.name,
            model=response.model,
            content=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason,
            raw_metadata={"response_id": response.id},
        )

    def list_models(self) -> list[str]:
        """Used only by the manual live-validation script -- never guess a
        model name; ask Groq what actually exists."""
        return [m.id for m in self._client.models.list().data]
