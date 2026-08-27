"""GroqProvider normalization/error-mapping tests -- no live API calls.
See tests/manual_groq_live_check.py for the one live integration path."""

from types import SimpleNamespace

import groq
import pytest

from controlplane.models.groq_provider import GroqProvider
from controlplane.models.provider import ModelProviderError, ModelProviderTimeout


def _fake_response(content="hi there", input_tokens=3, output_tokens=2, finish_reason="stop"):
    return SimpleNamespace(
        id="resp_123",
        model="fake-groq-model",
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=input_tokens, completion_tokens=output_tokens),
    )


class _FakeCompletions:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def create(self, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


class _FakeGroqClient:
    def __init__(self, response=None, exc=None, **kwargs):
        self.chat = SimpleNamespace(completions=_FakeCompletions(response=response, exc=exc))
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(data=[SimpleNamespace(id="m1")]))


def _provider_with_fake_client(monkeypatch, response=None, exc=None):
    monkeypatch.setattr(
        "controlplane.models.groq_provider.groq.Groq",
        lambda **kwargs: _FakeGroqClient(response=response, exc=exc),
    )
    return GroqProvider(api_key="fake-key", model="fake-model")


def test_generate_normalizes_a_successful_response(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, response=_fake_response())
    result = provider.generate(prompt="hello")
    assert result.provider == "groq"
    assert result.model == "fake-groq-model"
    assert result.content == "hi there"
    assert result.input_tokens == 3
    assert result.output_tokens == 2
    assert result.finish_reason == "stop"
    assert result.raw_metadata == {"response_id": "resp_123"}


def test_generate_maps_timeout_to_model_provider_timeout(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, exc=groq.APITimeoutError(request=None))
    with pytest.raises(ModelProviderTimeout):
        provider.generate(prompt="hello")


def test_generate_maps_groq_error_to_model_provider_error(monkeypatch):
    provider = _provider_with_fake_client(
        monkeypatch, exc=groq.APIConnectionError(request=None)
    )
    with pytest.raises(ModelProviderError):
        provider.generate(prompt="hello")


def test_constructor_rejects_missing_api_key():
    with pytest.raises(ModelProviderError):
        GroqProvider(api_key="", model="fake-model")


def test_constructor_rejects_missing_model():
    with pytest.raises(ModelProviderError):
        GroqProvider(api_key="fake-key", model="")


def test_list_models_returns_ids(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, response=_fake_response())
    assert provider.list_models() == ["m1"]
