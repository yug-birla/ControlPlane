"""GeminiProvider normalization/error-mapping/key-rotation tests -- no
live API calls. See tests/manual_gemini_live_check.py for the one live
integration path."""

from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from controlplane.models.gemini_provider import GeminiProvider
from controlplane.models.provider import ModelProviderError, ModelProviderTimeout


def _fake_response(content="hi there", input_tokens=3, output_tokens=2, finish_reason="STOP"):
    finish = SimpleNamespace(value=finish_reason) if finish_reason else None
    return SimpleNamespace(
        text=content,
        candidates=[SimpleNamespace(finish_reason=finish)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=input_tokens, candidates_token_count=output_tokens, total_token_count=input_tokens + output_tokens
        ),
    )


class _FakeModels:
    def __init__(self, response=None, exc=None, list_result=None):
        self._response = response
        self._exc = exc
        self._list_result = list_result or []

    def generate_content(self, **kwargs):
        if self._exc:
            raise self._exc
        return self._response

    def list(self):
        return self._list_result


class _FakeGeminiClient:
    def __init__(self, response=None, exc=None, list_result=None, **kwargs):
        self.models = _FakeModels(response=response, exc=exc, list_result=list_result)


def _provider_with_fake_client(monkeypatch, response=None, exc=None, api_keys=None):
    monkeypatch.setattr(
        "controlplane.models.gemini_provider.genai.Client",
        lambda **kwargs: _FakeGeminiClient(response=response, exc=exc),
    )
    return GeminiProvider(api_keys=api_keys or ["fake-key"], model="fake-model")


def test_generate_normalizes_a_successful_response(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, response=_fake_response())
    result = provider.generate(prompt="hello")
    assert result.provider == "gemini"
    assert result.model == "fake-model"
    assert result.content == "hi there"
    assert result.input_tokens == 3
    assert result.output_tokens == 2
    assert result.finish_reason == "STOP"


def test_generate_maps_client_error_to_model_provider_error(monkeypatch):
    exc = genai_errors.ClientError(code=400, response_json={"error": {"message": "bad request"}})
    provider = _provider_with_fake_client(monkeypatch, exc=exc)
    with pytest.raises(ModelProviderError):
        provider.generate(prompt="hello")


def test_generate_maps_server_error_to_model_provider_error(monkeypatch):
    exc = genai_errors.ServerError(code=500, response_json={"error": {"message": "server error"}})
    provider = _provider_with_fake_client(monkeypatch, exc=exc)
    with pytest.raises(ModelProviderError):
        provider.generate(prompt="hello")


def test_quota_error_on_first_key_falls_back_to_second_key(monkeypatch):
    quota_exc = genai_errors.ClientError(code=429, response_json={"error": {"message": "quota exceeded"}})
    calls = {"n": 0}
    clients = [_FakeGeminiClient(exc=quota_exc), _FakeGeminiClient(response=_fake_response())]

    def fake_client_factory(**kwargs):
        client = clients[calls["n"]]
        calls["n"] += 1
        return client

    monkeypatch.setattr("controlplane.models.gemini_provider.genai.Client", fake_client_factory)
    provider = GeminiProvider(api_keys=["key-1", "key-2"], model="fake-model")
    result = provider.generate(prompt="hello")
    assert result.content == "hi there"
    assert calls["n"] == 2


def test_quota_exhausted_on_all_keys_raises_model_provider_error(monkeypatch):
    quota_exc = genai_errors.ClientError(code=429, response_json={"error": {"message": "quota exceeded"}})
    monkeypatch.setattr(
        "controlplane.models.gemini_provider.genai.Client",
        lambda **kwargs: _FakeGeminiClient(exc=quota_exc),
    )
    provider = GeminiProvider(api_keys=["key-1", "key-2"], model="fake-model")
    with pytest.raises(ModelProviderError):
        provider.generate(prompt="hello")


def test_constructor_rejects_missing_api_keys():
    with pytest.raises(ModelProviderError):
        GeminiProvider(api_keys=[], model="fake-model")


def test_constructor_rejects_missing_model(monkeypatch):
    monkeypatch.setattr(
        "controlplane.models.gemini_provider.genai.Client",
        lambda **kwargs: _FakeGeminiClient(),
    )
    with pytest.raises(ModelProviderError):
        GeminiProvider(api_keys=["fake-key"], model="")


def test_list_models_filters_to_generate_content_capable(monkeypatch):
    list_result = [
        SimpleNamespace(name="models/gemini-2.5-flash", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/embedding-001", supported_actions=["embedContent"]),
    ]
    monkeypatch.setattr(
        "controlplane.models.gemini_provider.genai.Client",
        lambda **kwargs: _FakeGeminiClient(list_result=list_result),
    )
    provider = GeminiProvider(api_keys=["fake-key"], model="fake-model")
    assert provider.list_models() == ["models/gemini-2.5-flash"]
