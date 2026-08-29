"""Qwen 1.5B Judge vs Prometheus 2 (7B) on the hard grounding benchmark.

Milestone 10 (§21/§32). The Qwen judge was measured across Milestones
7-8 to collapse the middle class entirely -- **0/24 PARTIALLY_SUPPORTED
predictions**, unchanged by few-shot prompting. Prometheus 2 is
purpose-trained for evaluation, so it is the next justified step on the
improvement ladder (model comparison, before any fine-tuning).

The comparison keeps the existing Qwen judge rather than replacing it,
per the directive: whether Prometheus is actually better is a question
to be measured, not assumed from parameter count. The Milestone 10 model
tier comparison is a cautionary precedent -- there, the larger model
scored *worse*.

HARDWARE HONESTY: Prometheus 7B is ~14.5GB in bf16 against 15.7GB total
RAM on this machine. If it cannot load, this script reports
``NOT_MEASURED`` with the real error and exits cleanly. It does NOT
silently substitute a different model, estimate what the numbers might
have been, or quietly drop the comparison.

Run:
    .venv/Scripts/python -m controlplane.experiments.compare_judges
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_DATASET_PATH = Path("data/raw/generated/judge_hard_cases.json")
DATASET_ID = "judge_hard_cases"
DATASET_VERSION = "v0.1"
_LABELS = ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"]


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _score(predicted: list[str | None], expected: list[str]) -> dict:
    # A parse failure / missing prediction is scored as wrong, never
    # dropped -- silently excluding the cases a judge failed on would
    # flatter whichever judge fails more.
    predictions = [p or "UNPARSEABLE" for p in predicted]
    per_class = per_class_precision_recall_f1(expected, predictions, _LABELS)
    return {
        "sample_count": len(expected),
        "accuracy": accuracy(expected, predictions),
        "macro_f1": macro_f1(per_class),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(expected, predictions, _LABELS),
        "unparseable_count": sum(1 for p in predicted if p is None),
        "partially_supported_predicted": sum(1 for p in predictions if p == "PARTIALLY_SUPPORTED"),
    }


def _run_judge(judge, cases: list[dict], label: str) -> tuple[list[str | None], list[int]]:
    predictions: list[str | None] = []
    latencies: list[int] = []
    for i, case in enumerate(cases, 1):
        try:
            result = judge.evaluate(
                "grounding",
                query=case["query"],
                answer=case["answer"],
                evidence=case.get("evidence") or [],
            )
            predictions.append(result.label)
            latencies.append(result.latency_ms or 0)
            print(f"  [{i:>2}/{len(cases)}] {case['case_id']} {label}: "
                  f"{result.label} (expected {case['label']}) {result.latency_ms}ms")
        except Exception as exc:
            predictions.append(None)
            latencies.append(0)
            print(f"  [{i:>2}/{len(cases)}] {case['case_id']} {label}: ERROR {exc}")
    return predictions, latencies


def main() -> None:
    cases = _load()
    expected = [c["label"] for c in cases]
    print(f"Loaded {len(cases)} hard grounding cases\n")

    experiment_id = record_experiment(
        experiment_name="judge_model_comparison",
        component="llm_judge",
        algorithm="qwen_1.5b_vs_prometheus_7b",
        algorithm_version="v1",
    )
    results: dict = {}

    # --- Prometheus 7B (may not load on this hardware) ---
    print("=== Prometheus 2 (7B) ===")
    try:
        from controlplane.judge.prometheus_judge import get_prometheus_judge

        judge = get_prometheus_judge()
    except Exception as exc:
        print(f"  NOT_MEASURED -- Prometheus could not be loaded: {exc}")
        results["prometheus_7b"] = {
            "status": "NOT_MEASURED",
            "reason": str(exc)[:500],
            "note": "~14.5GB bf16 weights vs 15.7GB total RAM on this machine. "
                    "This is a RAM constraint, not the latency constraint the project "
                    "accepts elsewhere. No numbers are estimated in its place.",
        }
        judge = None

    if judge is not None:
        predictions, latencies = _run_judge(judge, cases, "prometheus")
        metrics = _score(predictions, expected)
        metrics["latency_ms_mean"] = sum(latencies) / len(latencies) if latencies else None
        results["prometheus_7b"] = {"status": "MEASURED", **metrics}
        run_id = record_run(
            experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
            model="prometheus-eval/prometheus-7b-v2.0",
            configuration={"prompt": "prometheus_absolute_grading", "rubric": "grounding_5pt"},
            notes="24 hand-authored hard grounding cases; CPU-only",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    # --- Qwen 1.5B judge (the incumbent, kept for comparison) ---
    print("\n=== Qwen2.5-1.5B Judge (incumbent) ===")
    try:
        from controlplane.judge.local_judge import get_local_judge

        qwen = get_local_judge()
        predictions, latencies = _run_judge(qwen, cases, "qwen")
        metrics = _score(predictions, expected)
        metrics["latency_ms_mean"] = sum(latencies) / len(latencies) if latencies else None
        results["qwen_1.5b"] = {"status": "MEASURED", **metrics}
        run_id = record_run(
            experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
            model="Qwen/Qwen2.5-1.5B-Instruct",
            configuration={"prompt": "repo_json_contract_with_fewshot"},
            notes="24 hand-authored hard grounding cases; CPU-only",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)
    except Exception as exc:
        print(f"  NOT_MEASURED -- {exc}")
        results["qwen_1.5b"] = {"status": "NOT_MEASURED", "reason": str(exc)[:500]}

    print("\n" + "=" * 72)
    for name, r in results.items():
        if r.get("status") != "MEASURED":
            print(f"{name:<18} {r['status']}: {r.get('reason','')[:60]}")
            continue
        print(f"{name:<18} accuracy={r['accuracy']:.3f} macro_f1={r['macro_f1']:.3f} "
              f"PARTIALLY_SUPPORTED predicted={r['partially_supported_predicted']}/{r['sample_count']} "
              f"unparseable={r['unparseable_count']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"judge_comparison_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID,
                   "dataset_version": DATASET_VERSION, "results": results}, f, indent=2, default=str)
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
