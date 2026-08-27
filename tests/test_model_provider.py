import pytest

from controlplane.config import Settings
from controlplane.errors import ConfigurationError
from controlplane.models.registry import get_configured_provider
from tests.fakes import FailingModelProvider, FakeModelProvider


def test_fake_provider_returns_normalized_result():
    provider = FakeModelProvider(content="hello world")
    result = provider.generate(prompt="hi")
    assert result.provider == "fake"
    assert result.content == "hello world"
    assert result.latency_ms >= 0
    assert provider.calls == ["hi"]


def test_registry_raises_configuration_error_without_api_key():
    settings = Settings(groq_api_key=None, groq_model="some-model")
    with pytest.raises(ConfigurationError):
        get_configured_provider(settings)


def test_registry_raises_configuration_error_without_model():
    settings = Settings(groq_api_key="sk-not-real", groq_model=None)
    with pytest.raises(ConfigurationError):
        get_configured_provider(settings)


def test_failing_provider_raises_model_provider_error():
    from controlplane.models.provider import ModelProviderError, ModelProviderTimeout

    with pytest.raises(ModelProviderError):
        FailingModelProvider().generate(prompt="hi")
    with pytest.raises(ModelProviderTimeout):
        FailingModelProvider(timeout=True).generate(prompt="hi")
