"""Model provider abstraction.

The rest of ControlPlane depends on ``ModelProvider``/``ModelResult``
only -- never on a specific SDK (e.g. the ``groq`` or ``google-genai``
packages). Only controlplane/models/groq_provider.py and
controlplane/models/gemini_provider.py may import those SDKs. See
docs/ALGORITHMS/MODEL_PROVIDER_ABSTRACTION.md.

Model routing (Layer 10) selects a *role* (FAST/STRONG); Gemini is a
separate, conservatively-used comparison provider, never the default
route -- see controlplane/models/registry.py and
docs/PROJECT_STATE/DECISIONS.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pydantic import BaseModel


class ModelResult(BaseModel):
    provider: str
    model: str
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int
    finish_reason: str | None = None
    raw_metadata: dict = {}
    """Safe, structured metadata only (e.g. finish_reason, id). Never the
    raw prompt/response text (that's ``content``/the caller's prompt) and
    never hidden chain-of-thought / reasoning tokens, even if the
    underlying API returns them."""


class ModelProviderError(Exception):
    """Base class for provider failures. controlplane.runtime maps these
    onto controlplane.errors.{DependencyError,TimeoutError}."""


class ModelProviderTimeout(ModelProviderError):
    pass


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, *, prompt: str) -> ModelResult: ...
