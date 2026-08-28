"""Offline local ModelProvider tests.

No real model load/generation here (that costs ~3s + CPU-bound decoding
per call) -- the LocalLLM is faked, exactly as tests/test_judge.py fakes
it. The one real end-to-end generation check is
tests/manual_local_generation_live_check.py.
"""

from __future__ import annotations

import pytest

from controlplane.models.local_generation_provider import LocalGenerationProvider
from controlplane.models.provider import ModelProviderError


class _FakeLLM:
    model_repo = "Qwen/Qwen2.5-1.5B-Instruct"
    model_revision = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"

    def __init__(self, text: str = "a real local answer", fail: bool = False) -> None:
        self._text = text
        self._fail = fail
        self.calls: list[tuple[list[dict], int]] = []

    def chat(self, messages, max_new_tokens):
        if self._fail:
            raise RuntimeError("decoder exploded")
        self.calls.append((messages, max_new_tokens))
        return self._text, 4321, 11, 7


def test_generate_returns_a_normalized_model_result_with_real_token_counts():
    provider = LocalGenerationProvider(role="STRONG", llm=_FakeLLM())
    result = provider.generate(prompt="what is the refund policy?")

    assert result.provider == "local_hf_generation"
    assert result.model == "Qwen/Qwen2.5-1.5B-Instruct"
    assert result.content == "a real local answer"
    # Real tokenizer counts passed through, not word-count estimates.
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.latency_ms == 4321
    assert result.raw_metadata["decoding"] == "greedy"
    assert result.raw_metadata["device"] == "cpu"


def test_fast_role_is_capped_shorter_than_strong_role():
    """On CPU, output length dominates latency -- this cap is where the
    FAST/STRONG distinction actually becomes a measurable cost difference
    for this single-model provider."""
    fast_llm, strong_llm = _FakeLLM(), _FakeLLM()
    LocalGenerationProvider(role="FAST", llm=fast_llm).generate(prompt="q")
    LocalGenerationProvider(role="STRONG", llm=strong_llm).generate(prompt="q")

    fast_max = fast_llm.calls[0][1]
    strong_max = strong_llm.calls[0][1]
    assert fast_max < strong_max


def test_prompt_is_passed_through_as_a_user_message():
    llm = _FakeLLM()
    LocalGenerationProvider(llm=llm).generate(prompt="the evidence-augmented prompt")
    messages = llm.calls[0][0]
    assert messages == [{"role": "user", "content": "the evidence-augmented prompt"}]


def test_generation_failure_maps_onto_the_provider_error_contract():
    """Runtime maps ModelProviderError -> DependencyError; a raw
    RuntimeError escaping from torch would bypass that mapping."""
    provider = LocalGenerationProvider(llm=_FakeLLM(fail=True))
    with pytest.raises(ModelProviderError):
        provider.generate(prompt="q")


def test_fast_and_strong_resolve_to_genuinely_different_models():
    """Milestone 10: through Milestone 9 both roles resolved to the same
    1.5B model, so "model escalation" changed a label and a token budget
    but not the model. Escalation results were therefore only a mechanism
    check, not a capability change."""
    from controlplane.models.local_generation_provider import _ROLE_MODELS

    fast_repo, _ = _ROLE_MODELS["FAST"]
    strong_repo, _ = _ROLE_MODELS["STRONG"]
    assert fast_repo != strong_repo


def test_every_tier_pins_an_exact_revision():
    """A model tier without a pinned revision is not reproducible."""
    from controlplane.models.local_generation_provider import _ROLE_MODELS

    for role, (repo, revision) in _ROLE_MODELS.items():
        assert repo and revision, f"{role} is missing repo/revision"
        assert len(revision) == 40, f"{role} revision {revision!r} is not a full commit sha"


def test_provider_reports_the_model_it_actually_used():
    """ModelResult.model must name the tier's real repo, so a routing
    decision can be audited against what actually ran."""
    llm = _FakeLLM()
    llm.model_repo = "Qwen/Qwen3-4B"
    result = LocalGenerationProvider(role="STRONG", llm=llm).generate(prompt="q")
    assert result.model == "Qwen/Qwen3-4B"
    assert result.raw_metadata["role"] == "STRONG"
