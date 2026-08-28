"""Local LLM Judge -- Qwen/Qwen2.5-1.5B-Instruct, revision
989aa7980e4cf806f80c7fef2b1adb7bc71aa306 (pinned; verified via the live
Hugging Face API), Apache-2.0, ~1.5B parameters, ~3GB in bf16.

Selected because its tokenizer was already partially staged in this
environment's Hugging Face cache before this milestone (a strong signal
it was the intended choice), it is instruction-tuned (needed for
reliable structured-JSON output), and it is small enough for CPU-only
inference to complete in bounded (if slow) time -- see
docs/EVALUATION/EVALUATOR_RESULTS.md for measured latency. A 0.5B variant
was considered for speed but rejected without evidence the 1.5B model
was actually too slow to use in a calibration/offline setting (bootstrap:
"do not avoid local models because of CPU latency").

Model loading and raw chat generation live in
``controlplane.models.local_llm`` (extracted in Milestone 9 when the
offline ``ModelProvider`` became a second consumer of the same model --
see that module for the bf16 / low_cpu_mem_usage / local_files_only /
thread-count rationale, each of which fixes a real reproduced failure).
This class owns only the judging concerns on top of it: the structured
JSON contract, prompt construction, and parse-failure handling.

MEASURED LATENCY (this machine, CPU-only, NO-GPU DEMONSTRATION
ENVIRONMENT -- bootstrap's local model latency policy: CPU latency is
accepted, not hidden): cold load ~3s; a single ~100-max-new-token
structured-JSON judgment ~30-70s (greedy decoding, no KV-cache
optimization beyond what ``transformers`` does by default, no
quantization). This is why the Local Judge is NOT wired into the live
per-request Evaluation Suite (``controlplane.evaluation.evaluators``,
sub-100ms per request) -- it is used for offline calibration/comparison
experiments and as an explicitly-invoked deeper-evaluation path, exactly
per bootstrap SS15/43: "LLM judges are not ground truth... use
selectively," not a claim that every request is judge-scored.
"""

from __future__ import annotations

from functools import lru_cache

from controlplane.judge.parsing import extract_json_object, safe_float
from controlplane.judge.prompts import build_judge_prompt
from controlplane.judge.schema import JudgeResult, JudgeStatus
from controlplane.models.local_llm import MODEL_REPO, MODEL_REVISION, LocalLLM, LocalLLMError

__all__ = ["MODEL_REPO", "MODEL_REVISION", "LocalJudge", "LocalJudgeError", "get_local_judge"]


class LocalJudgeError(Exception):
    pass


class LocalJudge:
    name = "local_qwen2.5-1.5b-instruct"

    def __init__(self, max_new_tokens: int = 100, llm: LocalLLM | None = None) -> None:
        """``llm`` may be an already-loaded instance so a process that
        needs both the judge and
        ``controlplane.models.local_generation_provider`` shares one ~3GB
        copy of the weights instead of loading it twice."""
        try:
            self._llm = llm if llm is not None else LocalLLM()
        except LocalLLMError as exc:
            raise LocalJudgeError(str(exc)) from exc
        self._max_new_tokens = max_new_tokens

    def _run_generate(self, messages: list[dict], max_new_tokens: int) -> tuple[str, int]:
        text, latency_ms, _input_tokens, _output_tokens = self._llm.chat(messages, max_new_tokens)
        return text, latency_ms

    def generate_answer(self, query: str, max_new_tokens: int | None = None) -> tuple[str, int]:
        """Plain free-text generation (not the judge's JSON contract) --
        used by ``controlplane.evaluation.bias`` to produce real paired
        answers for the Bias evaluator's counterfactual comparison when no
        live Groq/Gemini key is available this session (this repo's
        general-purpose local generative model pool is still deferred,
        see docs/PROJECT_STATE/DECISIONS.md, but this judge model is
        itself a real instruction-tuned generator and can fill that one
        narrow need honestly rather than faking paired answers)."""
        messages = [{"role": "user", "content": query}]
        return self._run_generate(messages, max_new_tokens or self._max_new_tokens)

    def evaluate(self, task: str, *, query: str, answer: str, evidence: list[str] | None = None) -> JudgeResult:
        system, user = build_judge_prompt(task, query=query, answer=answer, evidence=evidence)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        raw_output, latency_ms = self._run_generate(messages, self._max_new_tokens)

        parsed = extract_json_object(raw_output)
        if parsed is None:
            return JudgeResult(
                judge=self.name,
                task=task,
                status=JudgeStatus.PARSE_FAILED,
                rationale="local judge response was not parseable JSON",
                latency_ms=latency_ms,
                model=MODEL_REPO,
                raw_output=raw_output[:500],
            )
        return JudgeResult(
            judge=self.name,
            task=task,
            status=JudgeStatus.IMPLEMENTED,
            label=parsed.get("label"),
            score=safe_float(parsed.get("score")),
            issues=list(parsed.get("issues") or []),
            rationale=str(parsed.get("rationale", "")),
            latency_ms=latency_ms,
            model=MODEL_REPO,
            raw_output=raw_output[:500],
        )


@lru_cache(maxsize=1)
def get_local_judge() -> LocalJudge:
    return LocalJudge()
