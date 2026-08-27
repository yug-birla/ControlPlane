"""Query Profiler evaluation: Baseline A (rules) vs Baseline B (hybrid),
against the validation split -- never test/challenge (those stay held out
per docs/DATA/EVALUATION_PROTOCOL.md).

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_query_profiler

Ground truth caveat (repeated in every output artifact, not just here):
data/evaluation/validation/query_profiles_validation.json labels carry
provenance=SYNTHETIC (LLM-generated, docs/DATA/DATASET_GAPS.md) -- these
numbers measure agreement with another model's synthetic judgment, not
human ground truth.

Fields NOT evaluated here, and why:
- ``intent``: the dataset's ``intent`` field is a free-text description,
  not a label in this profiler's 12-value categorical scheme -- no
  ground truth exists in a comparable form.
- ``domain``: no fixed taxonomy exists (28+ distinct free-text values
  across ~270 records) -- reported qualitatively in
  docs/EVALUATION/QUERY_PROFILER_RESULTS.md, not as an accuracy number.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.metrics import (
    accuracy,
    confusion_matrix,
    macro_f1,
    multilabel_micro_macro_f1,
    per_class_precision_recall_f1,
)
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.query_intelligence.fingerprint import CapabilityHint
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler, _TAXONOMY_TO_CAPABILITY
from controlplane.query_intelligence.rules import RuleBasedQueryProfiler

_VALIDATION_PATH = Path("data/evaluation/validation/query_profiles_validation.json")
DATASET_ID = "query_profiles_validation"
DATASET_VERSION = "v0.1"

_CATEGORICAL_FIELDS = {
    "complexity": ["low", "medium", "high"],
    "sensitivity": ["NONE", "POTENTIAL_PII", "PII_EXPOSURE", "SENSITIVE_DATA_EXPOSURE"],
    "ambiguity": ["low", "medium", "high"],
    "actionability": [
        "informational", "analytical", "procedural", "generative", "decisional", "agentic", "pending_clarification",
    ],
}


def _expected_capability_hints(taxonomy_labels: list[str]) -> set[str]:
    hints = {_TAXONOMY_TO_CAPABILITY[l].value for l in taxonomy_labels if l in _TAXONOMY_TO_CAPABILITY}
    return hints or {CapabilityHint.GENERAL.value}


def _load_validation() -> list[dict]:
    with open(_VALIDATION_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def evaluate_profiler(profiler, records: list[dict]) -> dict:
    predictions = {field: [] for field in _CATEGORICAL_FIELDS}
    truths = {field: [] for field in _CATEGORICAL_FIELDS}
    hint_pred: list[set[str]] = []
    hint_true: list[set[str]] = []
    failures = []

    for record in records:
        try:
            fp = profiler.profile(record["query"])
        except Exception as exc:  # noqa: BLE001 -- record and continue, never crash the whole eval
            failures.append({"query_id": record["query_id"], "error": str(exc)})
            continue

        predictions["complexity"].append(fp.complexity.value)
        truths["complexity"].append(record["complexity"])
        predictions["sensitivity"].append(fp.sensitivity.value)
        truths["sensitivity"].append(record["sensitivity"])
        predictions["ambiguity"].append(fp.ambiguity.value)
        truths["ambiguity"].append(record["ambiguity"])
        predictions["actionability"].append(fp.actionability.value)
        truths["actionability"].append(record["actionability"])

        hint_pred.append({h.value for h in fp.capability_hints})
        hint_true.append(_expected_capability_hints(record["taxonomy_labels"]))

    metrics: dict = {"sample_count": len(records), "failures": failures, "fields": {}}
    for field, labels in _CATEGORICAL_FIELDS.items():
        y_true, y_pred = truths[field], predictions[field]
        per_class = per_class_precision_recall_f1(y_true, y_pred, labels)
        metrics["fields"][field] = {
            "accuracy": accuracy(y_true, y_pred),
            "macro_f1": macro_f1(per_class),
            "per_class": per_class,
            "confusion_matrix": confusion_matrix(y_true, y_pred, labels),
        }

    all_hint_labels = sorted({h.value for h in CapabilityHint})
    metrics["capability_hints"] = multilabel_micro_macro_f1(hint_true, hint_pred, all_hint_labels)
    metrics["not_measured"] = {
        "intent": "no ground truth in this categorical scheme -- dataset's intent field is free text",
        "domain": "no fixed taxonomy -- reported qualitatively only",
    }
    return metrics


def main() -> None:
    records = _load_validation()
    experiment_id = record_experiment(
        experiment_name="query_profiler_baseline_comparison",
        component="query_profiler",
        algorithm="rules_vs_hybrid",
        algorithm_version="v1",
    )

    results = {}
    for name, profiler in (("rules", RuleBasedQueryProfiler()), ("hybrid", HybridQueryProfiler())):
        metrics = evaluate_profiler(profiler, records)
        run_id = record_run(
            experiment_id=experiment_id,
            dataset_id=DATASET_ID,
            dataset_version=DATASET_VERSION,
            model=name,
            configuration={"profiler": name},
            notes=f"provenance=SYNTHETIC ground truth; see docs/EVALUATION/QUERY_PROFILER_RESULTS.md",
        )
        record_evaluation(experiment_run_id=run_id, split="validation", metrics=metrics)
        results[name] = {"run_id": run_id, "metrics": metrics}
        print(f"[{name}] complexity acc={metrics['fields']['complexity']['accuracy']:.3f} "
              f"sensitivity acc={metrics['fields']['sensitivity']['accuracy']:.3f} "
              f"ambiguity acc={metrics['fields']['ambiguity']['accuracy']:.3f} "
              f"actionability acc={metrics['fields']['actionability']['accuracy']:.3f} "
              f"capability_hints micro_f1={metrics['capability_hints']['micro_f1']:.3f} "
              f"macro_f1={metrics['capability_hints']['macro_f1']:.3f} "
              f"failures={len(metrics['failures'])}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"query_profiler_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "results": results}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
