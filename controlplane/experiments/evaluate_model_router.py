"""Model Router evaluation against the validation split.

No ground-truth "correct model" label exists in this dataset (the
routing spec's suggested ``preferred_action``/``expected_initial_route``
schema was never populated for this project's generated data -- the
closest field, ``expected_route``, is a free-text route family like
"rag_retrieval"/"reasoning", not a FAST/STRONG label), so this is not an
accuracy evaluation. Instead it measures the two things that actually
matter for this milestone (bootstrap SS63: "the final system must not
become less safe because of routing optimization"):

1. Action/role/cost-class distribution (descriptive -- what the baseline
   actually does on real query text).
2. A hard safety invariant, checked two ways: using our own measured
   Risk Profiler output (what the system would really do today), and
   using the dataset's ground-truth ``risk`` label directly (decoupling
   "is routing logic safe" from "is risk classification accurate",
   since the latter gap is already documented in
   docs/EVALUATION/RISK_PROFILER_RESULTS.md and must not be re-litigated
   here).

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_model_router
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from controlplane.experiments.evaluate_query_profiler import _load_validation
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.policy.baseline import PolicyBaseline
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import ControlDepth, RiskProfile, RiskSeverity
from controlplane.routing.model_router import ModelRouteAction, ModelRouter

DATASET_ID = "query_profiles_validation"
DATASET_VERSION = "v0.1"

_RISK_DIMS = ("factuality", "reasoning", "privacy", "pii", "security", "bias", "financial", "action", "safety")


def _ground_truth_risk_profile(severity: RiskSeverity) -> RiskProfile:
    """A synthetic RiskProfile carrying only the dataset's ground-truth
    severity -- used solely to test the Model Router's decision logic in
    isolation from Risk Profiler accuracy (see module docstring)."""
    return RiskProfile(
        risk_dimensions={d: severity for d in _RISK_DIMS},
        severity=severity,
        recommended_control_depth=ControlDepth.DEEP_PATH if severity in (RiskSeverity.HIGH_RISK, RiskSeverity.CRITICAL) else ControlDepth.FAST_PATH,
        source="ground_truth_label_for_evaluation_only",
    )


def evaluate(records: list[dict]) -> dict:
    profiler = HybridQueryProfiler()
    risk_profiler = BaselineRiskProfiler()
    policy = PolicyBaseline()
    router = ModelRouter()

    actions = Counter()
    roles = Counter()
    cost_classes = Counter()
    unsafe_predicted = []
    unsafe_ground_truth = []
    fast_model_savings = 0

    for record in records:
        fp = profiler.profile(record["query"])
        risk = risk_profiler.profile(record["query"], fp)
        policy_decision = policy.decide(risk.severity)
        decision = router.decide(fp, risk, policy_decision)

        actions[decision.action.value] += 1
        roles[decision.model_role or "NONE"] += 1
        cost_classes[decision.expected_cost_class] += 1
        if decision.action == ModelRouteAction.USE_FAST_MODEL:
            fast_model_savings += 1

        if risk.severity in (RiskSeverity.HIGH_RISK, RiskSeverity.CRITICAL) and (
            decision.action == ModelRouteAction.USE_FAST_MODEL or (decision.action != ModelRouteAction.ABSTAIN and not decision.require_verification)
        ):
            unsafe_predicted.append(record["query_id"])

        gt_severity = RiskSeverity(record["risk"])
        if gt_severity in (RiskSeverity.HIGH_RISK, RiskSeverity.CRITICAL):
            gt_policy = policy.decide(gt_severity)
            gt_decision = router.decide(fp, _ground_truth_risk_profile(gt_severity), gt_policy)
            if gt_decision.action == ModelRouteAction.USE_FAST_MODEL or (
                gt_decision.action != ModelRouteAction.ABSTAIN and not gt_decision.require_verification
            ):
                unsafe_ground_truth.append(record["query_id"])

    return {
        "sample_count": len(records),
        "action_distribution": dict(actions),
        "model_role_distribution": dict(roles),
        "expected_cost_class_distribution": dict(cost_classes),
        "fast_model_rate": f"{fast_model_savings}/{len(records)}",
        "cost_note": (
            f"{fast_model_savings}/{len(records)} queries routed to FAST instead of unconditionally "
            "using STRONG -- an estimated cost/latency reduction for those queries based on ESTIMATE "
            "cost classes, not a measured dollar/ms amount (no GROQ_API_KEY available this session, "
            "see docs/PROJECT_STATE/DECISIONS.md)."
        ),
        "unsafe_routes_using_predicted_risk": unsafe_predicted,
        "unsafe_routes_using_ground_truth_risk": unsafe_ground_truth,
        "safety_invariant": (
            "PASS: no example, under either our own predicted risk or the dataset's ground-truth risk "
            "label, reaches USE_FAST_MODEL (or verification-free execution) at HIGH_RISK/CRITICAL severity."
            if not unsafe_predicted and not unsafe_ground_truth
            else "FAIL: see unsafe_routes_* above -- this is a real safety regression, not a metric to relax."
        ),
    }


def main() -> None:
    records = _load_validation()
    experiment_id = record_experiment(
        experiment_name="model_router_baseline_evaluation",
        component="model_router",
        algorithm="threshold_v0",
        algorithm_version="v1",
    )
    metrics = evaluate(records)
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        model="threshold_v0",
        configuration={"profiler": "hybrid", "risk_profiler": "rules_and_fingerprint", "policy": "baseline"},
        notes="No ground-truth model label exists; this is a distribution + safety-invariant evaluation, not an accuracy evaluation. See docs/EVALUATION/ROUTING_RESULTS.md",
    )
    record_evaluation(experiment_run_id=run_id, split="validation", metrics=metrics)

    print(f"actions={metrics['action_distribution']} roles={metrics['model_role_distribution']} "
          f"safety_invariant={metrics['safety_invariant']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"model_router_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
