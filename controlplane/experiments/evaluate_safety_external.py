"""SERIOUS BENCHMARK (bootstrap section 58, not a smoke test) --
``PromptInjectionEvaluator`` against the full public
`deepset/prompt-injections` dataset (662 real examples, Apache-2.0),
normalized by `data/external/deepset_prompt_injections/fetch_and_normalize.py`.

This project's own hand-authored 12-case benchmark
(`docs/EVALUATION/EVALUATOR_RESULTS.md`) scored a clean 1.0 -- but a
fixed 18-phrase keyword list was always going to look perfect against
12 cases it was partly designed around. This is the honest test: real,
independently-authored injection attempts the evaluator's phrase list
was never tuned against.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_safety_external
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.evaluation.evaluators import EvaluationContext, PromptInjectionEvaluator
from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_DATASET_PATH = Path("data/external/deepset_prompt_injections/prompt_injections_normalized.json")
DATASET_ID = "deepset_prompt_injections"
DATASET_VERSION = "4f61ecb038e9c3fb77e21034b22511b523772cdd"
_LABELS = ["INJECTION_PATTERN_DETECTED", "NO_PATTERN_DETECTED"]


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    cases = _load()
    evaluator = PromptInjectionEvaluator()

    y_true, y_pred = [], []
    false_negatives, false_positives = [], []
    for case in cases:
        result = evaluator.evaluate(EvaluationContext(query=case["query"], answer="placeholder"))
        y_true.append(case["expected_label"])
        y_pred.append(result.label)
        if case["expected_label"] == "INJECTION_PATTERN_DETECTED" and result.label != "INJECTION_PATTERN_DETECTED":
            false_negatives.append({"case_id": case["case_id"], "query": case["query"]})
        if case["expected_label"] == "NO_PATTERN_DETECTED" and result.label == "INJECTION_PATTERN_DETECTED":
            false_positives.append({"case_id": case["case_id"], "query": case["query"]})

    per_class = per_class_precision_recall_f1(y_true, y_pred, _LABELS)
    metrics = {
        "sample_count": len(cases),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(per_class),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, _LABELS),
        "false_negative_count": len(false_negatives),
        "false_negative_rate": len(false_negatives) / sum(1 for t in y_true if t == "INJECTION_PATTERN_DETECTED"),
        "false_positive_count": len(false_positives),
        "false_positive_rate": len(false_positives) / sum(1 for t in y_true if t == "NO_PATTERN_DETECTED"),
        "false_negatives_sample": false_negatives[:15],
        "false_positives_sample": false_positives[:15],
    }

    experiment_id = record_experiment(
        experiment_name="prompt_injection_evaluator_external_benchmark",
        component="evaluation_safety",
        algorithm="prompt_injection_pattern_v0",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
        model="deterministic_pattern_match", configuration={},
        notes="SERIOUS BENCHMARK (662 real examples, not a smoke test) -- public deepset/prompt-injections dataset, Apache-2.0",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print(f"accuracy={metrics['accuracy']:.3f} macro_f1={metrics['macro_f1']:.3f}")
    print(f"false_negative_rate={metrics['false_negative_rate']:.3f} ({metrics['false_negative_count']} missed injections)")
    print(f"false_positive_rate={metrics['false_positive_rate']:.3f} ({metrics['false_positive_count']} benign queries wrongly flagged)")
    for label, stats in metrics["per_class"].items():
        print(f"  {label}: precision={stats['precision']:.2f} recall={stats['recall']:.2f} f1={stats['f1']:.2f} support={stats['support']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"prompt_injection_external_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
