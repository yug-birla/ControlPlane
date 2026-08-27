"""Test doubles shared across the test suite."""

from __future__ import annotations

from controlplane.models.provider import (
    ModelProvider,
    ModelProviderError,
    ModelProviderTimeout,
    ModelResult,
)


class FakeModelProvider(ModelProvider):
    name = "fake"

    def __init__(self, content: str = "a fake model response", latency_ms: int = 5) -> None:
        self._content = content
        self._latency_ms = latency_ms
        self.calls: list[str] = []

    def generate(self, *, prompt: str) -> ModelResult:
        self.calls.append(prompt)
        return ModelResult(
            provider=self.name,
            model="fake-model-1",
            content=self._content,
            input_tokens=len(prompt.split()),
            output_tokens=len(self._content.split()),
            latency_ms=self._latency_ms,
            finish_reason="stop",
        )


class FailingModelProvider(ModelProvider):
    name = "fake"

    def __init__(self, timeout: bool = False, message: str = "simulated provider failure") -> None:
        self._timeout = timeout
        self._message = message

    def generate(self, *, prompt: str) -> ModelResult:
        if self._timeout:
            raise ModelProviderTimeout(self._message)
        raise ModelProviderError(self._message)
