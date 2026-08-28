"""Safety / prompt-injection evaluator results -- bootstrap SS20
(InjecAgent research direction). Measures
``controlplane.evaluation.evaluators.PromptInjectionEvaluator`` against
a hand-authored benchmark that deliberately includes near-miss negative
cases (queries containing part of a trigger phrase in a benign sense)
to check for false positives, not just true positives.

Dataset: data/raw/generated/prompt_injection_cases.json (12 cases,
provenance HUMAN).

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_safety
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.evaluation.evaluators import EvaluationContext, PromptInjectionEvaluator
from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_DATASET_PATH = Path("data/raw/generated/prompt_injection_cases.json")
DATASET_ID = "prompt_injection_cases"
DATASET_VERSION = "v0.1"
_LABELS = ["INJECTION_PATTERN_DETECTED", "NO_PATTERN_DETECTED"]


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def main() -> None:
    cases = _load()
    evaluator = PromptInjectionEvaluator()

    y_true, y_pred = [], []
    errors = []
    for case in cases:
        result = evaluator.evaluate(EvaluationContext(query=case["query"], answer="placeholder"))
        y_true.append(case["expected_label"])
        y_pred.append(result.label)
        if result.label != case["expected_label"]:
            errors.append({"case_id": case["case_id"], "query": case["query"], "expected": case["expected_label"], "actual": result.label})

    per_class = per_class_precision_recall_f1(y_true, y_pred, _LABELS)
    metrics = {
        "sample_count": len(cases),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(per_class),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, _LABELS),
        "error_count": len(errors),
        "errors": errors,
    }

    experiment_id = record_experiment(
        experiment_name="prompt_injection_evaluator_baseline",
        component="evaluation_safety",
        algorithm="prompt_injection_pattern_v0",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
        model="deterministic_pattern_match", configuration={},
        notes="Includes deliberate near-miss negatives (partial phrase overlap in benign context) to check for false positives",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print(f"accuracy={metrics['accuracy']:.3f} macro_f1={metrics['macro_f1']:.3f} errors={metrics['error_count']}/{metrics['sample_count']}")
    for label, stats in metrics["per_class"].items():
        print(f"  {label}: precision={stats['precision']:.2f} recall={stats['recall']:.2f} f1={stats['f1']:.2f}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"prompt_injection_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
