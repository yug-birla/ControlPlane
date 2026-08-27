"""Requires the local embedding model to already be cached (see
controlplane/models/model_download.py)."""

import pytest

from controlplane.models.embedding_provider import EmbeddingProviderError
from controlplane.models.local_hf_provider import EMBEDDING_DIMENSION, LocalHFEmbeddingProvider


def test_embed_returns_correct_dimension_and_device():
    provider = LocalHFEmbeddingProvider()
    result = provider.embed(text="hello world")
    assert result.embedding_dimension == EMBEDDING_DIMENSION
    assert len(result.embedding) == EMBEDDING_DIMENSION
    assert result.device in ("cpu", "cuda", "mps")
    assert result.provider == "local_hf"
    assert result.latency_ms >= 0


def test_embed_batch_returns_one_result_per_input():
    provider = LocalHFEmbeddingProvider()
    results = provider.embed_batch(texts=["a", "b", "c"])
    assert len(results) == 3
    assert all(r.embedding_dimension == EMBEDDING_DIMENSION for r in results)


def test_loads_fully_offline_with_network_explicitly_disabled(monkeypatch):
    """Proves this is a cache-only load, not a disguised network call --
    bootstrap SS14: "Do not download a model during a user request." """
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    provider = LocalHFEmbeddingProvider()
    result = provider.embed(text="offline check")
    assert result.embedding_dimension == EMBEDDING_DIMENSION


def test_missing_local_model_fails_cleanly_instead_of_downloading(monkeypatch):
    """A pinned revision that was never downloaded must raise a clear,
    typed error -- never silently fall back to fetching it from the
    network mid-request."""
    monkeypatch.setattr("controlplane.models.local_hf_provider.MODEL_REVISION", "0000000000000000000000000000000000000000")
    with pytest.raises(EmbeddingProviderError, match="not cached locally"):
        LocalHFEmbeddingProvider()


def test_missing_sentence_transformers_package_reports_clearly(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("simulated: package not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(EmbeddingProviderError, match="not installed"):
        LocalHFEmbeddingProvider()
