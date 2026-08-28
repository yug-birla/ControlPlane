"""Manual/live LocalJudge validation -- NOT collected by pytest (doesn't
match ``test_*``), and never run in CI: a single call takes 30-90s on
this CPU-only machine (see docs/EVALUATION/EVALUATOR_RESULTS.md). Run
explicitly:

    .venv/Scripts/python -m tests.manual_local_judge_live_check

Requires Qwen/Qwen2.5-1.5B-Instruct (revision
989aa7980e4cf806f80c7fef2b1adb7bc71aa306) already downloaded locally --
see controlplane/judge/local_judge.py's module docstring.
"""

from __future__ import annotations

import sys

from controlplane.judge.local_judge import LocalJudge, LocalJudgeError


def main() -> int:
    try:
        judge = LocalJudge(max_new_tokens=80)
    except LocalJudgeError as exc:
        print("LOCAL JUDGE LIVE VALIDATION: NOT EXECUTED")
        print(f"Reason: {exc}")
        return 0

    result = judge.evaluate(
        "grounding",
        query="What is the meal reimbursement limit domestically?",
        answer="The meal limit is $75 per day domestically.",
        evidence=["Meal reimbursement is up to $75/day domestic, $100/day international."],
    )

    print("LOCAL JUDGE LIVE VALIDATION: EXECUTED")
    print(f"status: {result.status.value}")
    print(f"label: {result.label}")
    print(f"score: {result.score}")
    print(f"rationale: {result.rationale}")
    print(f"latency_ms: {result.latency_ms}")
    print(f"model: {result.model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
