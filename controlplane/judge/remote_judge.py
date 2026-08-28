"""Remote LLM Judge -- Gemini, via the same ``get_gemini_provider``
accessor already used by ``controlplane.experiments.compare_groq_vs_gemini``.
Never the live per-request path; used only by calibration/comparison
experiments (bootstrap SS14/41: "Gemini must be used conservatively...
never sent every response").
"""

from __future__ import annotations

import time

from controlplane.config import Settings
from controlplane.judge.parsing import extract_json_object, safe_float
from controlplane.judge.prompts import build_judge_prompt
from controlplane.judge.schema import JudgeResult, JudgeStatus
from controlplane.models.provider import ModelProviderError, ModelProviderTimeout
from controlplane.models.registry import get_gemini_provider


class RemoteJudge:
    name = "remote_gemini"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, task: str, *, query: str, answer: str, evidence: list[str] | None = None) -> JudgeResult:
        system, user = build_judge_prompt(task, query=query, answer=answer, evidence=evidence)
        prompt = f"{system}\n\n{user}"

        start = time.monotonic()
        try:
            provider = get_gemini_provider(self._settings)
            result = provider.generate(prompt=prompt)
        except (ModelProviderError, ModelProviderTimeout) as exc:
            return JudgeResult(
                judge=self.name,
                task=task,
                status=JudgeStatus.ERROR,
                rationale=f"remote judge call failed: {exc}",
                latency_ms=int((time.monotonic() - start) * 1000),
                model=self._settings.gemini_model or "unknown",
            )
        latency_ms = int((time.monotonic() - start) * 1000)

        parsed = extract_json_object(result.content)
        if parsed is None:
            return JudgeResult(
                judge=self.name,
                task=task,
                status=JudgeStatus.PARSE_FAILED,
                rationale="remote judge response was not parseable JSON",
                latency_ms=latency_ms,
                model=result.model,
                raw_output=result.content[:500],
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
            model=result.model,
            raw_output=result.content[:500],
        )
