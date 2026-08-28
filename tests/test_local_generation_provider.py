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
