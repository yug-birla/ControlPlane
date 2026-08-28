"""Offline local ``ModelProvider`` -- Qwen/Qwen2.5-1.5B-Instruct on CPU.

WHY THIS EXISTS (Milestone 9 architecture audit, P0 finding):

Through Milestone 8 the only real ``ModelProvider`` implementations were
Groq and Gemini, both requiring API keys. When no key is present -- which
has been the case for every session since Milestone 2 -- ``Runtime`` had
no generative model at all, so *every* end-to-end scenario, test, and
"baseline vs ControlPlane" measurement ran on scripted/fake providers
(``tests/fakes.FakeModelProvider``, the scripted providers in
``controlplane/experiments/evaluate_control_loop_before_after.py``).

That made the project's central claim -- "ControlPlane improves actual AI
execution" -- unmeasurable on real model output: the control loop was
only ever shown to change *hand-constructed* answers. This provider
closes that gap, because the same local model that already ships for
judging is a real instruction-tuned generator.

Using a deliberately small (1.5B) model is an ADVANTAGE for this
experiment, not a compromise: a 1.5B model genuinely hallucinates,
hedges, and answers without evidence, so the weaknesses ControlPlane
intervenes on are real model behavior rather than defects injected by
the experimenter. The comparison is therefore honest in the direction
that matters -- ControlPlane is not being handed pre-broken inputs.

NOT the default route. ``get_configured_provider`` still prefers Groq
when ``GROQ_API_KEY`` is set; this is selected only when
``CONTROLPLANE_LOCAL_GENERATION=1`` or when no remote key is configured
(see ``controlplane.models.registry``). Reason: CPU-only decoding is
slow (see MEASURED LATENCY below) and unsuitable as a default
interactive path, but entirely suitable for offline experiments,
demonstrations, and key-less operation.

MEASURED LATENCY: NO-GPU LOCAL INFERENCE, CPU-only. Cold model load ~3s;
generation scales with ``max_new_tokens`` (greedy, no quantization, no
KV-cache tuning beyond ``transformers`` defaults). See
docs/EVALUATION/BASELINE_VS_CONTROLPLANE.md for the measured
per-request numbers actually observed, not estimates.

Both FAST and STRONG roles resolve to this same model, differing only in
``max_new_tokens`` (FAST is shorter/cheaper). This is an honest,
documented limitation: it is a real latency/cost difference, but it is
NOT a genuine capability tier the way a 1.5B-vs-70B pair would be, so
model-escalation results measured against it must be read as
"escalation mechanism works", not "escalation reaches a smarter model".
"""

from __future__ import annotations

from functools import lru_cache

from controlplane.models.local_llm import LocalLLM, LocalLLMError
from controlplane.models.provider import ModelProvider, ModelProviderError, ModelResult

# FAST is capped shorter than STRONG: on CPU, output length dominates
# latency, so this is where the FAST/STRONG distinction actually shows up
# as a measurable cost difference for this provider.
_ROLE_MAX_NEW_TOKENS = {
    "FAST": 160,
    "STRONG": 320,
}
_DEFAULT_MAX_NEW_TOKENS = 320


class LocalGenerationProvider(ModelProvider):
    name = "local_hf_generation"

    def __init__(self, role: str = "STRONG", llm: LocalLLM | None = None) -> None:
        """``llm`` may be an already-loaded instance so a process that
        needs both this provider and the Local Judge shares one ~3GB copy
        of the weights instead of loading it twice."""
        try:
            self._llm = llm if llm is not None else LocalLLM()
        except LocalLLMError as exc:
            # Map onto the provider error contract so Runtime's existing
            # DependencyError/ConfigurationError mapping applies unchanged.
            raise ModelProviderError(str(exc)) from exc
        self._role = role
        self._max_new_tokens = _ROLE_MAX_NEW_TOKENS.get(role, _DEFAULT_MAX_NEW_TOKENS)

    def generate(self, *, prompt: str) -> ModelResult:
        messages = [{"role": "user", "content": prompt}]
        try:
            text, latency_ms, input_tokens, output_tokens = self._llm.chat(
                messages, max_new_tokens=self._max_new_tokens
            )
        except Exception as exc:  # generation-time failure, not a load failure
            raise ModelProviderError(f"local generation failed: {exc}") from exc

        return ModelResult(
            provider=self.name,
            model=self._llm.model_repo,
            content=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason="stop",
            raw_metadata={
                "model_revision": self._llm.model_revision,
                "role": self._role,
                "max_new_tokens": self._max_new_tokens,
                "decoding": "greedy",
                "device": "cpu",
            },
        )


@lru_cache(maxsize=2)  # one per role (FAST/STRONG); weights shared via _shared_llm
def get_local_generation_provider(role: str = "STRONG") -> LocalGenerationProvider:
    return LocalGenerationProvider(role=role, llm=_shared_llm())


@lru_cache(maxsize=1)
def _shared_llm() -> LocalLLM:
    """One loaded copy of the weights for every role in this process."""
    return LocalLLM()
