"""FAST vs STRONG local model tier comparison.

Milestone 10 (§16/§35/§96). Through Milestone 9 both Model Router roles
resolved to the SAME 1.5B model, so "model escalation" changed a label
and a token budget but not the model -- escalation results could only be
read as "the mechanism fires", never as "escalation reaches a more
capable model". The tiers are now genuinely different:

  FAST    Qwen/Qwen2.5-1.5B-Instruct
  STRONG  Qwen/Qwen3-4B

WHY SHORT-ANSWER ARITHMETIC AND FACT QUESTIONS: STRONG measures ~8 s per
generated token on this CPU (NO-GPU LOCAL INFERENCE), so a benchmark
with long outputs is latency-prohibited. Questions here are chosen to
have a single objectively checkable short answer, which keeps
``max_new_tokens`` small enough to run while still discriminating
capability. This is a deliberate scope limit, stated rather than hidden:
it measures short-form correctness, NOT long-form generation quality.

SCALE: SMOKE_TEST. This is a capability sanity check that justifies the
tiering, not a model benchmark.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_model_tiers
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.models.local_generation_provider import (
    _ROLE_MODELS,
    get_local_generation_provider,
)

# Each case: a question with one objectively checkable short answer.
# Deliberately mixes arithmetic (where a larger model is expected to
# help) with simple recall (where it should not) so the comparison can
# show *where* the tier matters rather than producing one blended number.
_CASES: list[dict] = [
    {"id": "MT-01", "category": "ARITHMETIC", "query": "What is 17 times 23? Give only the number.", "answer": "391"},
    {"id": "MT-02", "category": "ARITHMETIC", "query": "What is 144 divided by 12? Give only the number.", "answer": "12"},
    {"id": "MT-03", "category": "ARITHMETIC", "query": "What is 2847 plus 1965? Give only the number.", "answer": "4812"},
    {"id": "MT-04", "category": "ARITHMETIC", "query": "What is 15% of 240? Give only the number.", "answer": "36"},
    {"id": "MT-05", "category": "ARITHMETIC", "query": "A policy allows $75 per day. What is the total for 8 days? Give only the number.", "answer": "600"},
    {"id": "MT-06", "category": "REASONING", "query": "An expense of $12,000 falls in which band: $501-$5,000, $5,001-$25,000, or over $25,000? Answer with the band only.", "answer": "5,001"},
    {"id": "MT-07", "category": "REASONING", "query": "If notice is 30 days for staff and 60 for managers, how many days for a manager? Give only the number.", "answer": "60"},
    {"id": "MT-08", "category": "RECALL", "query": "What is the capital of France? Answer in one word.", "answer": "paris"},
    {"id": "MT-09", "category": "RECALL", "query": "How many days are in a leap year? Give only the number.", "answer": "366"},
    {"id": "MT-10", "category": "RECALL", "query": "What does the acronym SLA stand for? Answer in one short phrase.", "answer": "service level agreement"},
]

_MAX_NEW_TOKENS = 24  # short answers only -- see the module docstring


def _is_correct(answer: str, expected: str) -> bool:
    """Token-boundary match for numerics (so "12" does not match "120"),
    plain containment for word answers. Same discipline as the
    baseline-vs-ControlPlane scorer, where naive substring matching was a
    real measured bug."""
    text = (answer or "").lower()
    expected = expected.lower()
    if expected[0].isdigit():
        return re.search(rf"(?<![\w.]){re.escape(expected)}(?!\w)(?!\.\d)", text) is not None
    return expected in text


def _run_role(role: str) -> list[dict]:
    provider = get_local_generation_provider(role)
    provider._max_new_tokens = _MAX_NEW_TOKENS  # keep STRONG runnable on CPU

    rows = []
    for case in _CASES:
        try:
            result = provider.generate(prompt=case["query"])
            content, latency, out_tokens = result.content, result.latency_ms, result.output_tokens
            model = result.model
            failed = False
        except Exception as exc:
            content, latency, out_tokens, model, failed = "", 0, 0, "ERROR", True
            print(f"  {case['id']}: FAILURE {exc}")

        correct = _is_correct(content, case["answer"])
        rows.append({
            "case_id": case["id"], "category": case["category"], "role": role, "model": model,
            "expected": case["answer"], "answer": content[:200],
            "correct": correct, "latency_ms": latency, "output_tokens": out_tokens,
            "provider_failed": failed,
        })
        print(f"  {case['id']} [{case['category']:<10}] {role:<6} correct={str(correct):<5} "
              f"{latency:>6}ms  {content[:44]!r}")
    return rows


def _aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    latencies = [r["latency_ms"] for r in rows]
    tokens = sum(r["output_tokens"] or 0 for r in rows)
    return {
        "sample_count": n,
        "accuracy": sum(1 for r in rows if r["correct"]) / n if n else None,
        "accuracy_by_category": {
            cat: sum(1 for r in rs if r["correct"]) / len(rs) for cat, rs in by_cat.items()
        },
        "latency_ms_mean": sum(latencies) / n if n else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "output_tokens_total": tokens,
        "ms_per_output_token": (sum(latencies) / tokens) if tokens else None,
    }


def main() -> None:
    experiment_id = record_experiment(
        experiment_name="local_model_tier_comparison",
        component="model_routing",
        algorithm="fast_vs_strong_local_tier",
        algorithm_version="v1",
    )

    results = {}
    all_rows = []
    for role in ("FAST", "STRONG"):
        repo, revision = _ROLE_MODELS[role]
        print(f"\n=== {role}: {repo} ===")
        rows = _run_role(role)
        all_rows += rows
        metrics = _aggregate(rows)
        results[role] = {"model": repo, "revision": revision, **metrics}
        run_id = record_run(
            experiment_id=experiment_id,
            dataset_id="model_tier_cases", dataset_version="v0.1",
            model=f"{role}:{repo}", configuration={"role": role, "max_new_tokens": _MAX_NEW_TOKENS},
            notes="SMOKE_TEST (10 short-answer cases); CPU-only local inference; "
                  "measures short-form correctness only, not long-form generation quality",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print("\n" + "=" * 74)
    print(f"{'METRIC':<34}{'FAST':>18}{'STRONG':>18}")
    print("=" * 74)
    f, s = results["FAST"], results["STRONG"]
    print(f"{'model':<34}{f['model'].split('/')[-1]:>18}{s['model'].split('/')[-1]:>18}")
    print(f"{'accuracy':<34}{f['accuracy']:>18.3f}{s['accuracy']:>18.3f}")
    for cat in sorted(set(f["accuracy_by_category"]) | set(s["accuracy_by_category"])):
        print(f"{'  ' + cat:<34}{f['accuracy_by_category'].get(cat, 0):>18.3f}"
              f"{s['accuracy_by_category'].get(cat, 0):>18.3f}")
    print(f"{'latency_ms_mean':<34}{f['latency_ms_mean']:>18.0f}{s['latency_ms_mean']:>18.0f}")
    print(f"{'ms_per_output_token':<34}{f['ms_per_output_token'] or 0:>18.0f}"
          f"{s['ms_per_output_token'] or 0:>18.0f}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"model_tiers_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": experiment_id, "results": results, "rows": all_rows},
                  fh, indent=2, default=str)
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
