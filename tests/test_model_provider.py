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


def test_registry_falls_back_to_the_local_model_without_an_api_key(monkeypatch):
    """Milestone 9 contract change (deliberate, not a regression): a
    key-less environment used to raise ConfigurationError, which left the
    whole system with no generative model and forced every end-to-end
    scenario onto scripted fakes. It now falls back to the offline local
    provider. See controlplane/models/local_generation_provider.py.

    CONTRACT CHANGE 2026-08-30: STRONG now resolves through a failover
    chain, so its fallback happens at generate() time rather than at
    construction. The GUARANTEE is unchanged and is asserted at both
    levels below -- a key-less environment still ends up on the local
    model, whichever role asked.
    """
    sentinel = object()
    monkeypatch.setattr(
        "controlplane.models.local_generation_provider.get_local_generation_provider",
        lambda role: sentinel,
    )
    settings = Settings(groq_api_key=None, groq_model="some-model")

    # FAST still resolves eagerly.
    assert get_configured_provider(settings, role="FAST") is sentinel

    # STRONG returns the chain; local is its floor and must be reached.
    chain = get_configured_provider(settings, role="STRONG")
    assert [c.name for c in chain.candidates][-1] == "local_hf_generation"


def test_registry_reports_configuration_error_when_no_provider_is_available_at_all(monkeypatch):
    """No remote key AND no cached local weights is still a real, clean
    configuration failure -- the fallback must not silently swallow it."""
    from controlplane.models.provider import ModelProviderError

    def _unavailable(role):
        raise ModelProviderError("weights not cached")

    monkeypatch.setattr(
        "controlplane.models.local_generation_provider.get_local_generation_provider",
        _unavailable,
    )
    settings = Settings(groq_api_key=None, groq_model="some-model")

    # FAST: the eager path still raises a clean configuration error.
    with pytest.raises(ConfigurationError):
        get_configured_provider(settings, role="FAST")

    # STRONG: the chain has nothing usable, and says so at call time
    # rather than pretending it produced an answer.
    from controlplane.models.provider import ModelProviderError

    chain = get_configured_provider(settings, role="STRONG")
    with pytest.raises(ModelProviderError):
        chain.generate(prompt="hi")
    assert [a.outcome for a in chain.attempts] == ["UNAVAILABLE"] * 3


def test_local_generation_is_preferred_when_explicitly_forced(monkeypatch):
    """CONTROLPLANE_LOCAL_GENERATION=1 pins the reproducible local model
    even when a remote key is present (used by offline experiments)."""
    sentinel = object()
    monkeypatch.setattr(
        "controlplane.models.local_generation_provider.get_local_generation_provider",
        lambda role: sentinel,
    )
    settings = Settings(groq_api_key="sk-not-real", groq_model="m", use_local_generation=True)
    assert get_configured_provider(settings) is sentinel


def test_registry_raises_configuration_error_without_model():
    settings = Settings(groq_api_key="sk-not-real", groq_model=None)
    # The eager (FAST) path. A model name is never hard-coded, so a key
    # without a model is a configuration error rather than a guess.
    with pytest.raises(ConfigurationError):
        get_configured_provider(settings, role="FAST")


def test_failing_provider_raises_model_provider_error():
    from controlplane.models.provider import ModelProviderError, ModelProviderTimeout

    with pytest.raises(ModelProviderError):
        FailingModelProvider().generate(prompt="hi")
    with pytest.raises(ModelProviderTimeout):
        FailingModelProvider(timeout=True).generate(prompt="hi")
