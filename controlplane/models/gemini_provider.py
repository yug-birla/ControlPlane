"""Gemini adapter -- the only module in ControlPlane allowed to import the
``google-genai`` SDK (the current unified Google GenAI Python SDK,
package ``google-genai``, import path ``google.genai`` -- verified live
against PyPI this milestone, not assumed from training data; the older
``google-generativeai`` package is stale, see docs/PROJECT_STATE/DECISIONS.md).
Everything else uses controlplane.models.provider.ModelProvider.

SECURITY: API keys are passed in by the caller (read from
controlplane.config.Settings.gemini_api_keys, which reads
GEMINI_API_KEY_1/GEMINI_API_KEY_2 from the environment). This module
never logs, stores, or echoes them.

Per instruction, Gemini has limited/non-free quota in this deployment
and must be used conservatively (never the default route) -- see
controlplane/routing/model_router.py and docs/PROJECT_STATE/DECISIONS.md.
Two keys are supported for quota headroom: on a quota/rate-limit error
(HTTP 429) from one key, the provider retries with the next key before
giving up.
"""

from __future__ import annotations

import time

from google import genai
from google.genai import errors as genai_errors

from controlplane.models.provider import (
    ModelProvider,
    ModelProviderError,
    ModelProviderTimeout,
    ModelResult,
)


class GeminiProvider(ModelProvider):
    name = "gemini"

    def __init__(self, api_keys: list[str], model: str, timeout: float = 30.0) -> None:
        api_keys = [k for k in api_keys if k]
        if not api_keys:
            raise ModelProviderError("no GEMINI_API_KEY_* is configured")
        if not model:
            raise ModelProviderError("GEMINI_MODEL is not configured")
        self._clients = [
            genai.Client(api_key=key, http_options=genai.types.HttpOptions(timeout=int(timeout * 1000)))
            for key in api_keys
        ]
        self._model = model

    def generate(self, *, prompt: str) -> ModelResult:
        start = time.monotonic()
        last_exc: Exception | None = None
        for client in self._clients:
            try:
                response = client.models.generate_content(model=self._model, contents=prompt)
                break
            except genai_errors.ClientError as exc:
                last_exc = exc
                if exc.code == 429:
                    continue  # quota exhausted on this key -- try the next one
                raise ModelProviderError(str(exc)) from exc
            except genai_errors.ServerError as exc:
                raise ModelProviderError(str(exc)) from exc
            except TimeoutError as exc:
                raise ModelProviderTimeout(str(exc)) from exc
        else:
            raise ModelProviderError(f"all configured Gemini keys exhausted quota: {last_exc}") from last_exc

        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage_metadata
        candidate = response.candidates[0] if response.candidates else None
        return ModelResult(
            provider=self.name,
            model=self._model,
            content=response.text or "",
            input_tokens=usage.prompt_token_count if usage else None,
            output_tokens=usage.candidates_token_count if usage else None,
            latency_ms=latency_ms,
            finish_reason=candidate.finish_reason.value if candidate and candidate.finish_reason else None,
            raw_metadata={"total_token_count": usage.total_token_count if usage else None},
        )

    def list_models(self) -> list[str]:
        """Used only by the manual live-validation script -- never guess a
        model name; ask Gemini what actually exists."""
        return [
            m.name for m in self._clients[0].models.list()
            if m.supported_actions and "generateContent" in m.supported_actions
        ]
