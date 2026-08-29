"""Prometheus 2 (7B) local LLM Judge.

Model: ``prometheus-eval/prometheus-7b-v2.0``, revision
``66ffb1fc20beebfb60a3964a957d9011723116c5``, Apache-2.0, Mistral-7B
architecture, ~14.5GB in bf16.

WHY: ``docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md`` names
"Prometheus 2 (7B-class)" as the intended judge model. Through Milestone
9 the only judge was Qwen2.5-1.5B, which was measured to collapse the
middle ``PARTIALLY_SUPPORTED`` class entirely (0/24 predictions across
the hard benchmark, unchanged by few-shot prompting in Milestone 8).
Prometheus 2 is purpose-trained for evaluation, so it is the next
justified step on the improvement ladder -- model comparison, before any
fine-tuning.

PROMPT FORMAT is Prometheus 2's own, not this repo's generic judge
prompt. The model was trained on a specific absolute-grading template
(task description, instruction, response, optional reference answer,
score rubric, then "Feedback: ... [RESULT] N"). Feeding it this repo's
JSON-output contract instead would be using a specialist model off-
distribution and would measure the prompt mismatch rather than the
model. The output is parsed back onto this repo's existing
``JudgeResult`` contract so the rest of the system is unchanged.

NO HIDDEN CHAIN-OF-THOUGHT: Prometheus emits a "feedback" rationale
before its score. That text is a *rationale*, which this repo already
persists for the Qwen judge (``JudgeResult.rationale``) -- it is the
model's stated justification, not a hidden reasoning trace, and it is
truncated on storage like every other judge output.

HARDWARE REALITY (measured on this machine, reported not hidden):
15.7GB total RAM with ~4.9GB free at the time of writing, against a
~14.5GB bf16 model. This is a RAM constraint, not the latency constraint
the project has accepted elsewhere, and it may make this judge
unloadable here. ``load()`` surfaces that as a clean, typed error rather
than letting the process thrash the page file -- the same failure class
as the Milestone 6 ``OSError: paging file is too small``, one order of
magnitude larger. If it cannot load, that is recorded as a blocker with
concrete options, never worked around by silently substituting a
different model.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from controlplane.judge.schema import JudgeResult, JudgeStatus

MODEL_REPO = "prometheus-eval/prometheus-7b-v2.0"
MODEL_REVISION = "66ffb1fc20beebfb60a3964a957d9011723116c5"

# Offloaded layers live on E: alongside the models, never on the
# near-full C: drive (see BLOCKERS.md B10 for why that matters here).
_OFFLOAD_DIR = Path("E:/ControlPlane/data/models/offload/prometheus-7b-v2")


class PrometheusJudgeError(Exception):
    pass


# ~14.5GB of bf16 weights, plus headroom for activations and the KV
# cache during generation. Deliberately not padded further: the point is
# to refuse the clearly-impossible case, not to gatekeep a marginal one.
_REQUIRED_RAM_GB = 15.0


def _available_ram_gb() -> float | None:
    """Available physical RAM, or ``None`` when it cannot be determined.

    Returning ``None`` (rather than a guess) means the pre-flight check
    is skipped and the load is attempted -- an unknown environment should
    not be blocked by a check that cannot see it.
    """
    try:  # psutil is not a dependency of this project; use it only if present
        import psutil

        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        pass
    try:
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullAvailPhys / (1024 ** 3)
    except Exception:
        pass
    return None


# Prometheus 2's absolute-grading template, as published for the model.
_ABSOLUTE_TEMPLATE = """###Task Description:
An instruction (might include an Input inside it), a response to evaluate, and a score rubric representing a evaluation criteria are given.
1. Write a detailed feedback that assess the quality of the response strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5. You should refer to the score rubric.
3. The output format should look as follows: "Feedback: (write a feedback for criteria) [RESULT] (an integer number between 1 and 5)"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
{instruction}

###Response to evaluate:
{response}

###Score Rubrics:
{rubric}

###Feedback: """

# Rubric for the grounding task, phrased so the 5-point scale maps onto
# this repo's existing four-value grounding vocabulary rather than
# inventing a parallel one.
_GROUNDING_RUBRIC = """[Is the response fully supported by the provided evidence, without adding unsupported claims or contradicting it?]
Score 1: The response contradicts the evidence, or asserts specific facts the evidence does not contain at all.
Score 2: The response is mostly unsupported; only incidental details match the evidence.
Score 3: The response is partially supported -- some claims are backed by the evidence and others are not.
Score 4: The response is supported by the evidence, with only minor unsupported elaboration.
Score 5: Every substantive claim in the response is directly supported by the provided evidence."""

# 5-point score -> this repo's grounding labels. The middle of the scale
# is exactly the PARTIALLY_SUPPORTED class the Qwen judge could never
# predict, which is the specific weakness this model is being tried for.
_SCORE_TO_GROUNDING_LABEL = {
    1: "UNSUPPORTED",
    2: "UNSUPPORTED",
    3: "PARTIALLY_SUPPORTED",
    4: "SUPPORTED",
    5: "SUPPORTED",
}


def build_prometheus_prompt(*, query: str, answer: str, evidence: list[str] | None) -> str:
    evidence_block = "\n".join(f"- {e}" for e in (evidence or [])) or "(no evidence provided)"
    instruction = (
        f"Question: {query}\n\n"
        f"Evidence available to answer the question:\n{evidence_block}"
    )
    return _ABSOLUTE_TEMPLATE.format(
        instruction=instruction, response=answer, rubric=_GROUNDING_RUBRIC
    )


def parse_prometheus_output(raw: str) -> tuple[int | None, str]:
    """Returns ``(score, feedback)``. Score is ``None`` when the model did
    not follow the ``[RESULT] N`` contract -- reported as a parse failure
    rather than guessed, exactly as the Qwen judge does."""
    match = re.search(r"\[RESULT\]\s*([1-5])", raw)
    score = int(match.group(1)) if match else None
    feedback = raw.split("[RESULT]")[0].replace("Feedback:", "").strip()
    return score, feedback


class PrometheusJudge:
    name = "prometheus-7b-v2.0"

    def __init__(self, max_new_tokens: int = 256, offload: bool = True) -> None:
        """``offload=True`` streams layers that do not fit in RAM from
        disk via ``accelerate``.

        This is what makes the model runnable at all on this machine
        (~14.5GB bf16 vs 15.7GB total RAM). It is a real trade: a
        forward pass must read the offloaded layers from disk every
        token, so generation is dramatically slower than a resident
        model. The project's stated position is that CPU latency is
        acceptable and quality comes first, so slow-but-working is
        preferred to not-running -- but the cost is large enough that it
        bounds how many cases can be benchmarked, and that bound is
        reported rather than worked around.
        """
        try:
            import os

            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise PrometheusJudgeError("transformers/torch are not installed") from exc

        torch.set_num_threads(os.cpu_count() or 4)

        # PRE-FLIGHT RAM CHECK -- refuse rather than thrash.
        #
        # Measured on this machine (Milestone 10): attempting the bf16
        # load with ~0.3GB free drove the process into page-file
        # thrashing -- resident set grew ~0.15GB/min while burning four
        # cores, i.e. ~40 minutes to *maybe* finish loading, with every
        # subsequent judgment thrashing identically. It does not fail
        # fast; it degrades the whole machine. transformers has no
        # "refuse if it will not fit" option, so this is that option.
        required_gb = _REQUIRED_RAM_GB
        available_gb = _available_ram_gb()
        if not offload and available_gb is not None and available_gb < required_gb:
            raise PrometheusJudgeError(
                f"refusing to load {MODEL_REPO} fully resident: needs ~{required_gb:.1f}GB "
                f"(bf16) but only {available_gb:.1f}GB RAM is available. Loading anyway "
                "does not fail fast -- it page-thrashes for tens of minutes and degrades "
                "the whole machine (measured). Use offload=True, or see "
                "docs/PROJECT_STATE/BLOCKERS.md B12."
            )

        load_kwargs: dict = {
            "revision": MODEL_REVISION,
            "local_files_only": True,
            "dtype": torch.bfloat16,
            "low_cpu_mem_usage": True,
        }
        if offload:
            # Cap resident weights well below available RAM and stream the
            # remainder from disk. accelerate manages the paging itself
            # rather than leaving it to the OS page file, which is what
            # thrashed. The offload folder lives on E: with the models,
            # never on the near-full C:.
            budget_gb = max(4, int((available_gb or 8) - 2))
            load_kwargs.update(
                device_map="auto",
                max_memory={"cpu": f"{budget_gb}GiB"},
                offload_folder=str(_OFFLOAD_DIR),
                offload_state_dict=True,
            )
            _OFFLOAD_DIR.mkdir(parents=True, exist_ok=True)

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                MODEL_REPO, revision=MODEL_REVISION, local_files_only=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(MODEL_REPO, **load_kwargs)
        except Exception as exc:
            raise PrometheusJudgeError(
                f"{MODEL_REPO}@{MODEL_REVISION} could not be loaded. On this machine the "
                "binding constraint is RAM (~14.5GB bf16 weights vs 15.7GB total), not "
                f"latency. Underlying error: {exc}"
            ) from exc
        self._max_new_tokens = max_new_tokens

    def evaluate(
        self, task: str, *, query: str, answer: str, evidence: list[str] | None = None
    ) -> JudgeResult:
        import time

        if task != "grounding":
            return JudgeResult(
                judge=self.name, task=task, status=JudgeStatus.NOT_IMPLEMENTED,
                rationale=f"no Prometheus rubric is defined for task {task!r}; "
                          "a rubric must be written and reviewed before this model is "
                          "used for it, not improvised at call time",
                latency_ms=0, model=MODEL_REPO,
            )

        prompt = build_prometheus_prompt(query=query, answer=answer, evidence=evidence)
        messages = [{"role": "user", "content": prompt}]
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer([text], return_tensors="pt")

        start = time.monotonic()
        output_ids = self._model.generate(
            **inputs, max_new_tokens=self._max_new_tokens, do_sample=False,
            pad_token_id=self._tokenizer.eos_token_id,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        raw = self._tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        ).strip()

        score, feedback = parse_prometheus_output(raw)
        if score is None:
            return JudgeResult(
                judge=self.name, task=task, status=JudgeStatus.PARSE_FAILED,
                rationale="Prometheus response did not contain a [RESULT] score",
                latency_ms=latency_ms, model=MODEL_REPO, raw_output=raw[:500],
            )

        return JudgeResult(
            judge=self.name, task=task, status=JudgeStatus.IMPLEMENTED,
            label=_SCORE_TO_GROUNDING_LABEL[score],
            score=score / 5.0,
            rationale=feedback[:500],
            latency_ms=latency_ms, model=MODEL_REPO, raw_output=raw[:500],
        )


@lru_cache(maxsize=1)
def get_prometheus_judge() -> PrometheusJudge:
    return PrometheusJudge()
