"""Risk Profiler evaluation against the validation split's ``risk`` field
(the only risk ground truth the dataset carries -- per-dimension labels
for factuality/reasoning/privacy/etc. don't exist, so only overall
``severity`` is evaluated against ground truth; per-dimension outputs are
reported but not accuracy-scored).

Ground truth caveat: provenance=SYNTHETIC, same as
docs/EVALUATION/QUERY_PROFILER_RESULTS.md.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_risk_profiler
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import RiskSeverity

_VALIDATION_PATH = Path("data/evaluation/validation/query_profiles_validation.json")
DATASET_ID = "query_profiles_validation"
DATASET_VERSION = "v0.1"
_SEVERITY_LABELS = [s.value for s in RiskSeverity]
_HIGH_RISK_LABELS = {"HIGH_RISK", "CRITICAL"}


def _load_validation() -> list[dict]:
    with open(_VALIDATION_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def main() -> None:
    records = _load_validation()
    profiler_fp = HybridQueryProfiler()
    profiler_risk = BaselineRiskProfiler()

    y_true, y_pred = [], []
    high_risk_true, high_risk_caught = [], []
    per_dimension_examples: dict[str, list[str]] = {}

    for record in records:
        fp = profiler_fp.profile(record["query"])
        risk = profiler_risk.profile(record["query"], fp)

        y_true.append(record["risk"])
        y_pred.append(risk.severity.value)

        is_high_true = record["risk"] in _HIGH_RISK_LABELS
        high_risk_true.append(is_high_true)
        high_risk_caught.append(risk.severity.value in _HIGH_RISK_LABELS)

        for dim, sev in risk.risk_dimensions.items():
            if sev != RiskSeverity.NO_ACTION:
                per_dimension_examples.setdefault(dim, []).append(f"{record['query_id']}:{sev.value}")

    per_class = per_class_precision_recall_f1(y_true, y_pred, _SEVERITY_LABELS)
    n_true_high = sum(high_risk_true)
    missed_high = sum(1 for t, c in zip(high_risk_true, high_risk_caught) if t and not c)
    false_positive_high = sum(1 for t, c in zip(high_risk_true, high_risk_caught) if not t and c)
    critical_miss_rate = (missed_high / n_true_high) if n_true_high else "NOT_MEASURED (0 HIGH_RISK/CRITICAL examples in validation split)"

    metrics = {
        "sample_count": len(records),
        "overall_severity": {
            "accuracy": accuracy(y_true, y_pred),
            "macro_f1": macro_f1(per_class),
            "per_class": per_class,
            "confusion_matrix": confusion_matrix(y_true, y_pred, _SEVERITY_LABELS),
        },
        "high_risk_analysis": {
            "true_high_or_critical_count": n_true_high,
            "missed_high_or_critical_count": missed_high,
            "critical_miss_rate": critical_miss_rate,
            "false_positive_high_count": false_positive_high,
            "note": "false negatives on HIGH_RISK/CRITICAL prioritized per bootstrap SS19 -- a missed high-risk case is worse than a false alarm",
        },
        "per_dimension_trigger_examples": per_dimension_examples,
        "not_measured": {
            "per_dimension_accuracy": "no per-dimension ground truth exists in the dataset (only an aggregate 'risk' field) -- only overall severity is accuracy-scored",
        },
    }

    print(f"overall severity accuracy={metrics['overall_severity']['accuracy']:.3f} "
          f"macro_f1={metrics['overall_severity']['macro_f1']:.3f} "
          f"high_risk_true={n_true_high} missed={missed_high} false_positives={false_positive_high}")

    experiment_id = record_experiment(
        experiment_name="risk_profiler_baseline",
        component="risk_profiler",
        algorithm="rules_and_fingerprint",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
        model="rules_and_fingerprint",
        notes="provenance=SYNTHETIC ground truth; only overall severity has ground truth to score against",
    )
    record_evaluation(experiment_run_id=run_id, split="validation", metrics=metrics)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"risk_profiler_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "run_id": run_id, "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
