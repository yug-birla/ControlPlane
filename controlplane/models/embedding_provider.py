"""Embedding provider abstraction -- deliberately separate from
``ModelProvider`` (controlplane/models/provider.py).

An embedding call returns a vector, not generated text; forcing it
through the generation-shaped interface would be a misuse of that
abstraction rather than a reuse of it. See
docs/PROJECT_STATE/DECISIONS.md for this call. The two hierarchies share
the same design principle (the rest of ControlPlane depends only on the
interface, never a specific SDK/framework) without sharing a base class
that doesn't actually fit both shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class EmbeddingResult(BaseModel):
    provider: str
    model: str
    embedding: list[float]
    embedding_dimension: int
    latency_ms: int
    device: str
    raw_metadata: dict = {}


class EmbeddingProviderError(Exception):
    pass


class EmbeddingProvider(ABC):
    name: str

    @abstractmethod
    def embed(self, *, text: str) -> EmbeddingResult: ...

    @abstractmethod
    def embed_batch(self, *, texts: list[str]) -> list[EmbeddingResult]: ...
