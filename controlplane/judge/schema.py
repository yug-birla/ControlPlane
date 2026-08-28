"""LLM-as-a-Judge -- structured output contract shared by every judge
implementation (Local/Remote), per bootstrap SS13: "The judge should
return structured output: evaluator, status, label, score, confidence
where justified, evidence, issues, rationale, recommended_signal. Do NOT
expose hidden chain-of-thought. Only store structured reasoning
summaries."

Judges are never asked to "think step by step" or produce a scratchpad;
the prompt (``controlplane.judge.prompts``) asks directly for the final
JSON object, so ``rationale`` is a short structured summary by
construction, not a redacted chain-of-thought.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class JudgeStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    """The judge produced a well-formed, parseable structured result."""
    PARSE_FAILED = "PARSE_FAILED"
    """The judge responded but its output could not be parsed as the
    expected JSON contract -- never silently coerced into a fabricated
    label/score."""
    ERROR = "ERROR"
    """The underlying model call itself failed (timeout, provider error,
    local model unavailable)."""


class JudgeResult(BaseModel):
    judge: str
    """Which judge produced this -- e.g. "local_qwen2.5-1.5b-instruct" or
    "remote_gemini"."""
    task: str
    """Which evaluation task this judged -- e.g. "grounding", "quality",
    "reasoning", "safety"."""
    status: JudgeStatus
    label: str | None = None
    score: float | None = None
    confidence: float | None = None
    issues: list[str] = Field(default_factory=list)
    rationale: str
    recommended_signal: str | None = None
    latency_ms: int
    model: str
    raw_output: str = ""
    """Kept for debugging/calibration -- the judge's literal (short,
    structured-JSON) response text, not a hidden reasoning trace."""
