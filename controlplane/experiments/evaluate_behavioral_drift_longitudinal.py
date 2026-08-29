"""How good is behavioural drift detection, really? (§37)

SEPARATE FILE ON PURPOSE. ``evaluate_behavioral_drift.py`` is a
self-labelled 4-case baseline DEMONSTRATION with a committed result
file from 2026-08-28. Replacing it would have destroyed a reproducible
historical experiment (§6), so this is an additional measurement
alongside it, not a rewrite of it.

The existing result for this component is `4 cases, 4 matched, rate
1.000`. That is a demonstration, not a measurement: four cases chosen
alongside the implementation, all passing, with no false-positive guard
and no case the representation could fail on.

This runs the SHIPPED ``BehavioralDriftDetector`` unchanged against 22
longitudinal trajectories (365 history entries) built to include
categories it is expected to MISS. That is deliberate. A dataset
assembled only from what a component already handles cannot produce a
finding, and §37 asks for precision, recall, false positives and false
negatives -- all of which require cases that can fail.

WHAT THE DETECTOR REPRESENTS. ``(tool, governance_action)`` frequency
against history. So it can see "this tool is unprecedented" and "this
outcome is unprecedented". It structurally cannot see workflow length,
destination class, read-only-to-mutating transitions, or a TREND across
a trajectory -- and the dataset contains all four.

TWO METRICS, BECAUSE THEY ANSWER DIFFERENT QUESTIONS:

  exact level accuracy   did it produce the right NONE/LOW/MEDIUM/HIGH?
  alert decision         did it fire at all when it should have, and
                         stay quiet when it should have? This is what a
                         human actually experiences, and a detector can
                         be useful with imperfect levels but useless
                         with bad alert behaviour.

Run (deterministic, no model, seconds):
    .venv/Scripts/python -m controlplane.experiments.evaluate_behavioral_drift_longitudinal
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.governance.behavioral_drift import BehavioralDriftDetector

_CASES = Path("data/raw/generated/behavioral_drift_cases.json")
_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH")
_ALERTING = {"MEDIUM", "HIGH"}


def _load() -> list[dict]:
    with open(_CASES, encoding="utf-8-sig") as f:
        return json.load(f)


def _metrics(rows: list[dict]) -> dict:
    n = len(rows) or 1
    should_alert = [r for r in rows if r["expected"] in _ALERTING]
    should_stay_quiet = [r for r in rows if r["expected"] not in _ALERTING]
    false_alarms = [r for r in should_stay_quiet if r["actual"] in _ALERTING]
    missed = [r for r in should_alert if r["actual"] not in _ALERTING]

    per_level = {}
    for level in _LEVELS:
        tp = sum(1 for r in rows if r["actual"] == level and r["expected"] == level)
        fp = sum(1 for r in rows if r["actual"] == level and r["expected"] != level)
        fn = sum(1 for r in rows if r["actual"] != level and r["expected"] == level)
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        per_level[level] = {
            "support": sum(1 for r in rows if r["expected"] == level),
            "precision": p, "recall": rc,
            "f1": (2 * p * rc / (p + rc)) if p + rc else 0.0,
        }

    return {
        "sample_count": len(rows),
        "exact_level_accuracy": sum(1 for r in rows if r["actual"] == r["expected"]) / n,
        "alert_decision_accuracy": sum(
            1 for r in rows if (r["actual"] in _ALERTING) == (r["expected"] in _ALERTING)) / n,
        "false_alarm_count": len(false_alarms),
        "false_alarm_rate": len(false_alarms) / (len(should_stay_quiet) or 1),
        "missed_drift_count": len(missed),
        "missed_drift_rate": len(missed) / (len(should_alert) or 1),
        "macro_f1": sum(v["f1"] for v in per_level.values()) / len(_LEVELS),
        "per_level": per_level,
        "false_alarm_cases": [r["case_id"] for r in false_alarms],
        "missed_cases": [r["case_id"] for r in missed],
    }


def _run(detector, cases: list[dict]) -> list[dict]:
    rows = []
    for case in cases:
        history = [(tool, action) for tool, action in case["history"]]
        assessment = detector.assess(
            history=history,
            proposed_tool=case["proposed_tool"],
            governance_action=case["governance_action"],
        )
        rows.append({
            "case_id": case["case_id"],
            "split": case.get("split", "all"),
            "drift_type": case["drift_type"],
            "history_length": case["history_length"],
            "expected": case["expected_level"],
            "actual": assessment.level.value,
            "correct": assessment.level.value == case["expected_level"],
            "reason": assessment.reason,
        })
    return rows


def main() -> None:
    cases = _load()
    detector = BehavioralDriftDetector()
    rows = _run(detector, cases)
    metrics = _metrics(rows)
    per_split = {name: _metrics([r for r in rows if r["split"] == name])
                 for name in sorted({r["split"] for r in rows})}

    experiment_id = record_experiment(
        experiment_name="behavioral_drift_longitudinal",
        component="behavioral_drift",
        algorithm="tool_action_frequency_v1",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id, dataset_id="behavioral_drift_cases",
        dataset_version="v1", model="deterministic", configuration={"rare_tool_threshold": 0.1},
        notes="22 longitudinal trajectories, 365 history entries; shipped detector unchanged",
    )
    record_evaluation(experiment_run_id=run_id, split=None,
                      metrics={k: v for k, v in metrics.items() if not isinstance(v, (list, dict))})

    print(f"{'case':<9}{'drift_type':<26}{'hist':>5}  {'expected':<9}{'actual':<9}{'ok':<4}")
    print("-" * 68)
    for r in rows:
        print(f"{r['case_id']:<9}{r['drift_type'][:25]:<26}{r['history_length']:>5}  "
              f"{r['expected']:<9}{r['actual']:<9}{'Y' if r['correct'] else 'N':<4}")

    print("\n" + "=" * 68)
    for key in ("sample_count", "exact_level_accuracy", "alert_decision_accuracy",
                "false_alarm_count", "false_alarm_rate", "missed_drift_count",
                "missed_drift_rate", "macro_f1"):
        value = metrics[key]
        print(f"  {key:<28}{value:.3f}" if isinstance(value, float) else f"  {key:<28}{value}")
    print("\n  per level:")
    for level, v in metrics["per_level"].items():
        print(f"    {level:<8} support={v['support']:<3} precision={v['precision']:.3f} "
              f"recall={v['recall']:.3f} f1={v['f1']:.3f}")
    print(f"\n  false alarms: {metrics['false_alarm_cases']}")
    print(f"  missed:       {metrics['missed_cases']}")

    print("\n  missed, by drift type (what the representation cannot see):")
    missed_types = Counter(r["drift_type"] for r in rows
                           if r["expected"] in _ALERTING and r["actual"] not in _ALERTING)
    for drift_type, count in missed_types.most_common():
        print(f"    {drift_type:<26}{count}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"behavioral_drift_longitudinal_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "metrics": metrics,
                   "per_split": per_split, "rows": rows}, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
