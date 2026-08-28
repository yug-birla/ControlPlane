"""Agent Governance gate evaluation against
``data/raw/generated/agent_trajectories.json`` (75 trajectories,
provenance SYNTHETIC, real ``expected_control_action`` labels -- never
previously consumed by any code, per docs/PROJECT_STATE/FUTURE_WORK.md
before this milestone).

Ground truth uses a 6-value vocabulary (KEEP, BLOCK, HUMAN_REVIEW,
ABSTAIN, CHANGE_DATA_SOURCE, DECREASE_COMPUTE); ``AgentGate`` uses a
narrower 4-value one (ALLOW, RESTRICT, HUMAN_REVIEW, BLOCK) matching
bootstrap SS32's own vocabulary. Mapped for comparison as:

    KEEP               -> ALLOW          (continue as proposed)
    BLOCK              -> BLOCK           (direct match)
    HUMAN_REVIEW       -> HUMAN_REVIEW    (direct match)
    ABSTAIN            -> HUMAN_REVIEW    (a cautious deferral, closer to
                                            "needs oversight" than either
                                            continuing or hard-blocking)
    CHANGE_DATA_SOURCE -> RESTRICT        (dataset intent: don't continue
                                            via the same path)
    DECREASE_COMPUTE   -> RESTRICT        (dataset intent: proceed, but
                                            constrained)

CHANGE_DATA_SOURCE/DECREASE_COMPUTE are POST-HOC recovery/cost
strategies keyed to the tool call's *result* (e.g. a 404 error), not the
proposed action's *inherent* risk -- ``AgentGate`` is a pre-execution
authorization gate and has no signal for "this already failed, try a
different source." Per-class metrics below make this gap visible rather
than hiding it behind one aggregate accuracy number.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_agent_governance
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.governance.agent_gate import AgentGate

_DATASET_PATH = Path("data/raw/generated/agent_trajectories.json")
DATASET_ID = "agent_trajectories"
DATASET_VERSION = "v0.1"
_LABELS = ["ALLOW", "RESTRICT", "HUMAN_REVIEW", "BLOCK"]

_GROUND_TRUTH_MAP = {
    "KEEP": "ALLOW",
    "BLOCK": "BLOCK",
    "HUMAN_REVIEW": "HUMAN_REVIEW",
    "ABSTAIN": "HUMAN_REVIEW",
    "CHANGE_DATA_SOURCE": "RESTRICT",
    "DECREASE_COMPUTE": "RESTRICT",
}


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _gated_step(trajectory: dict) -> dict:
    point = trajectory.get("intervention_point")
    steps = trajectory["steps"]
    if point and 1 <= point <= len(steps):
        return steps[point - 1]
    return steps[-1]


def evaluate(gate: AgentGate, records: list[dict]) -> dict:
    y_true, y_pred = [], []
    errors = []
    for record in records:
        step = _gated_step(record)
        decision = gate.evaluate_step(step["tool_call"], step_risk=step["risk"])
        expected = _GROUND_TRUTH_MAP[record["expected_control_action"]]
        y_true.append(expected)
        y_pred.append(decision.action.value)
        if decision.action.value != expected:
            errors.append({
                "trajectory_id": record["trajectory_id"],
                "trajectory_type": record["trajectory_type"],
                "tool_call": step["tool_call"],
                "step_risk": step["risk"],
                "expected_raw_label": record["expected_control_action"],
                "expected_mapped": expected,
                "actual": decision.action.value,
                "reason": decision.reason,
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
    }


def main() -> None:
    records = _load()
    experiment_id = record_experiment(
        experiment_name="agent_governance_gate_baseline",
        component="agent_governance",
        algorithm="agent_gate_v0",
        algorithm_version="v1",
    )
    gate = AgentGate()
    metrics = evaluate(gate, records)
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        model="agent_gate_v0",
        configuration={},
        notes=(
            "6-value ground truth collapsed to the gate's 4-value vocabulary (see module docstring); "
            "gate is a pre-execution proposed-action risk check, not a post-hoc recovery-strategy selector -- "
            "expect most disagreement in the RESTRICT class (CHANGE_DATA_SOURCE/DECREASE_COMPUTE)"
        ),
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print(f"accuracy={metrics['accuracy']:.3f} macro_f1={metrics['macro_f1']:.3f} errors={metrics['error_count']}/{metrics['sample_count']}")
    for label, stats in metrics["per_class"].items():
        print(f"  {label}: precision={stats['precision']:.2f} recall={stats['recall']:.2f} f1={stats['f1']:.2f} support={stats['support']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"agent_governance_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
