"""Reasoning evaluator capability audit -- bootstrap SS19: "Build a
reasoning benchmark containing easy reasoning, multi-step reasoning,
arithmetic, comparison, constraint satisfaction, deliberately misleading
questions."

This is NOT a conventional accuracy benchmark: ``ReasoningEvaluator``
(controlplane/evaluation/evaluators.py) is an explicitly narrow
deterministic self-contradiction check (direct polarity-pair assertions
about the same subject), not a general reasoning-quality evaluator --
see its docstring. Most cases in this dataset are labeled with what the
CURRENT evaluator actually reports (including on cases where that
report is a known, structural gap: arithmetic errors, numeric
comparison errors, unsupported causal leaps, cross-subject polarity) --
this measures and documents the real boundary of what the narrow check
covers, per bootstrap's "do not claim reasoning-validated if only
self-contradiction was checked."

Dataset: data/raw/generated/reasoning_cases.json (12 cases, provenance
HUMAN).

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_reasoning
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.evaluation.evaluators import EvaluationContext, ReasoningEvaluator
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_DATASET_PATH = Path("data/raw/generated/reasoning_cases.json")
DATASET_ID = "reasoning_cases"
DATASET_VERSION = "v0.1"

# Categories where the evaluator's own SELF_CONTRADICTORY detection is
# actually designed to work -- everything else is a documented,
# structural gap (arithmetic, comparison, causal-leap, cross-subject
# polarity), not something this V0 check claims to catch.
_IN_SCOPE_CATEGORIES = {"direct_self_contradiction_same_subject"}


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def main() -> None:
    cases = _load()
    evaluator = ReasoningEvaluator()

    matched = 0
    in_scope_correct = 0
    in_scope_total = 0
    out_of_scope_gap_confirmed = 0
    out_of_scope_total = 0
    per_case = []

    for case in cases:
        result = evaluator.evaluate(EvaluationContext(query=case["query"], answer=case["answer"]))
        label_matches_expected = result.label == case["expected_label"]
        matched += label_matches_expected
        in_scope = case["category"] in _IN_SCOPE_CATEGORIES
        if in_scope:
            in_scope_total += 1
            in_scope_correct += label_matches_expected
        else:
            out_of_scope_total += 1
            # For out-of-scope categories, "matches expected" means the
            # documented gap is confirmed (the evaluator behaves exactly
            # as its own limitations describe) -- not a success metric.
            out_of_scope_gap_confirmed += label_matches_expected
        per_case.append({
            "case_id": case["case_id"], "category": case["category"], "in_scope": in_scope,
            "expected_label": case["expected_label"], "actual_label": result.label,
            "matches_expected": label_matches_expected, "note": case.get("note", ""),
        })

    metrics = {
        "sample_count": len(cases),
        "label_matches_expected_rate": matched / len(cases),
        "in_scope_recall": (in_scope_correct / in_scope_total) if in_scope_total else "NOT_MEASURED",
        "in_scope_sample_count": in_scope_total,
        "out_of_scope_gap_confirmed_rate": (out_of_scope_gap_confirmed / out_of_scope_total) if out_of_scope_total else "NOT_MEASURED",
        "out_of_scope_sample_count": out_of_scope_total,
        "per_case": per_case,
    }

    experiment_id = record_experiment(
        experiment_name="reasoning_evaluator_capability_audit",
        component="evaluation_reasoning",
        algorithm="self_contradiction_check_v1",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
        model="deterministic_self_contradiction_check", configuration={},
        notes="Capability audit, not a conventional accuracy benchmark -- most cases document a real, structural scope boundary (arithmetic/comparison/causal-leap errors are not detectable by a polarity-pair self-contradiction check)",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print(f"in_scope_recall={metrics['in_scope_recall']} ({in_scope_correct}/{in_scope_total} same-subject contradictions correctly flagged)")
    print(f"out_of_scope_gap_confirmed_rate={metrics['out_of_scope_gap_confirmed_rate']} ({out_of_scope_gap_confirmed}/{out_of_scope_total})")
    print("Known, structural gaps (arithmetic errors, numeric-comparison errors, unsupported causal leaps, "
          "cross-subject polarity) require either a small local evaluator or an LLM judge -- see "
          "controlplane.evaluation.judge_evaluators.JudgeBackedEvaluator(task='reasoning') for the "
          "already-built (offline-calibration-only) alternative.")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"reasoning_evaluator_audit_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
