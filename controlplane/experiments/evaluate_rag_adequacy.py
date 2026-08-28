"""RAG Adequacy evaluation against ``data/raw/generated/rag_cases.json``
(150 examples, provenance SYNTHETIC). Ground truth field:
``evidence_sufficiency`` (SUFFICIENT / PARTIALLY_SUFFICIENT / INSUFFICIENT
-- no CONFLICTING example exists in this dataset, see
docs/EVALUATION/RAG_RESULTS.md).

Evaluates the adequacy LOGIC directly against the dataset's own supplied
``documents`` evidence text -- not this milestone's retrieval pipeline
(which runs against a different, real document corpus that this
dataset's inline evidence snippets don't literally correspond to; see
controlplane/rag/adequacy.py's module docstring).

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_rag_adequacy
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.rag.adequacy import RAGAdequacyEvaluator

_DATASET_PATH = Path("data/raw/generated/rag_cases.json")
DATASET_ID = "rag_cases"
DATASET_VERSION = "v0.1"
_LABELS = ["SUFFICIENT", "PARTIALLY_SUFFICIENT", "INSUFFICIENT"]


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def evaluate(evaluator: RAGAdequacyEvaluator, records: list[dict]) -> dict:
    y_true, y_pred = [], []
    errors = []
    for record in records:
        result = evaluator.assess(record["query"], record["documents"])
        y_true.append(record["evidence_sufficiency"])
        y_pred.append(result.label.value)
        if result.label.value != record["evidence_sufficiency"]:
            errors.append({
                "case_id": record["case_id"],
                "query": record["query"],
                "expected": record["evidence_sufficiency"],
                "actual": result.label.value,
                "coverage": result.coverage,
                "rag_category": record.get("rag_category"),
                "failure_mode": record.get("failure_mode"),
            })

    per_class = per_class_precision_recall_f1(y_true, y_pred, _LABELS)
    return {
        "sample_count": len(records),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(per_class),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, _LABELS),
        "error_count": len(errors),
        "errors_sample": errors[:15],
        "not_measured": {
            "CONFLICTING label": "no ground-truth example carries this label in this dataset -- see docs/EVALUATION/RAG_RESULTS.md",
        },
    }


def main() -> None:
    records = _load()
    experiment_id = record_experiment(
        experiment_name="rag_adequacy_baseline",
        component="rag_adequacy",
        algorithm="coverage_overlap_v0",
        algorithm_version="v1",
    )
    evaluator = RAGAdequacyEvaluator()
    metrics = evaluate(evaluator, records)
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        model="coverage_overlap_v0",
        configuration={"sufficient_threshold": evaluator._sufficient, "partial_threshold": evaluator._partial},
        notes="provenance=SYNTHETIC ground truth; evaluated against dataset-supplied evidence text, not this milestone's own retrieval pipeline (different corpus); thresholds grid-searched on this same dataset, no held-out split -- see docs/EVALUATION/RAG_RESULTS.md",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print(f"accuracy={metrics['accuracy']:.3f} macro_f1={metrics['macro_f1']:.3f} errors={metrics['error_count']}/{metrics['sample_count']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"rag_adequacy_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
