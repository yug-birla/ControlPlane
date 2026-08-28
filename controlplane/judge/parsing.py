"""Robust-but-honest JSON extraction from a judge's raw text response.
Small/instruction-tuned models occasionally wrap JSON in markdown fences
or add a stray leading/trailing word despite being told not to; this
recovers from that formatting noise WITHOUT ever inventing field values
that weren't actually present -- a genuinely unparseable response returns
``None`` (the caller reports ``JudgeStatus.PARSE_FAILED``), never a
fabricated result.
"""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(text: str) -> dict | None:
    text = text.strip()

    fence_match = _FENCE_RE.search(text)
    candidate = fence_match.group(1) if fence_match else text

    start = candidate.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(candidate)):
        if candidate[i] == "{":
            depth += 1
        elif candidate[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(candidate[start : i + 1])
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
