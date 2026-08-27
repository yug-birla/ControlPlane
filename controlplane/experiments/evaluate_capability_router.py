"""Capability Router evaluation against the validation split (same
dataset/ground-truth-derivation as evaluate_query_profiler.py's
capability_hints metric -- see that module for the ground-truth caveat:
provenance=SYNTHETIC).

This evaluation measures what the Capability Router *adds* on top of
the already-measured Query Profiler capability_hints (policy filtering
+ graph construction), not capability_hints accuracy itself (that
number is docs/EVALUATION/QUERY_PROFILER_RESULTS.md's, and re-measuring
it here would be redundant since restriction essentially never fires on
this dataset -- see the coverage-gap finding below).

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_capability_router
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.evaluate_query_profiler import _expected_capability_hints, _load_validation
from controlplane.experiments.metrics import multilabel_micro_macro_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.policy.baseline import PolicyBaseline
from controlplane.query_intelligence.fingerprint import CapabilityHint
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import RiskSeverity
from controlplane.routing.capability_router import CapabilityRouter

DATASET_ID = "query_profiles_validation"
DATASET_VERSION = "v0.1"


def evaluate(records: list[dict]) -> dict:
    profiler = HybridQueryProfiler()
    risk_profiler = BaselineRiskProfiler()
    policy = PolicyBaseline()
    router = CapabilityRouter()

    pred: list[set[str]] = []
    true: list[set[str]] = []
    restriction_events = []
    graph_validation_failures = []
    high_risk_agent_coverage = 0

    for record in records:
        fp = profiler.profile(record["query"])
        risk = risk_profiler.profile(record["query"], fp)
        policy_decision = policy.decide(risk.severity)
        route = router.route(fp, risk, policy_decision)

        pred.append(set(route.selected_capabilities))
        true.append(_expected_capability_hints(record["taxonomy_labels"]))

        if route.restricted_removed:
            restriction_events.append({
                "query_id": record["query_id"],
                "restricted": route.restricted_removed,
                "policy_tier": policy_decision.tier.value,
            })
        if risk.severity in (RiskSeverity.HIGH_RISK, RiskSeverity.CRITICAL) and CapabilityHint.AGENT.value in {
            h.value for h in fp.capability_hints
        }:
            high_risk_agent_coverage += 1

        try:
            route.graph.validate()
        except Exception as exc:  # noqa: BLE001
            graph_validation_failures.append({"query_id": record["query_id"], "error": str(exc)})

    all_labels = sorted({h.value for h in CapabilityHint})
    metrics = {
        "sample_count": len(records),
        "capability_set_after_routing": multilabel_micro_macro_f1(true, pred, all_labels),
        "restriction_events": restriction_events,
        "restriction_rate": f"{len(restriction_events)}/{len(records)}",
        "graph_validation_failures": graph_validation_failures,
        "graph_validation_pass_rate": f"{len(records) - len(graph_validation_failures)}/{len(records)}",
        "high_risk_examples_with_agent_hint_in_this_dataset": high_risk_agent_coverage,
        "coverage_note": (
            "0 (or very few) validation examples combine a ground-truth/predicted HIGH_RISK "
            "severity with an AGENT capability hint, so the AGENT-restriction safety path is "
            "exercised by unit tests (tests/test_capability_router.py, tests/test_model_router.py), "
            "not by this dataset. This is a coverage gap in the validation dataset, not a claim "
            "that restriction was untested."
        ),
    }
    return metrics


def main() -> None:
    records = _load_validation()
    experiment_id = record_experiment(
        experiment_name="capability_router_routing_evaluation",
        component="capability_router",
        algorithm="rules_v0",
        algorithm_version="v1",
    )
    metrics = evaluate(records)
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        model="capability_router_rules_v0",
        configuration={"profiler": "hybrid", "risk_profiler": "rules_and_fingerprint", "policy": "baseline"},
        notes="provenance=SYNTHETIC ground truth; see docs/EVALUATION/ROUTING_RESULTS.md",
    )
    record_evaluation(experiment_run_id=run_id, split="validation", metrics=metrics)

    print(f"capability_set micro_f1={metrics['capability_set_after_routing']['micro_f1']:.3f} "
          f"macro_f1={metrics['capability_set_after_routing']['macro_f1']:.3f} "
          f"restriction_rate={metrics['restriction_rate']} "
          f"graph_validation_pass_rate={metrics['graph_validation_pass_rate']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"capability_router_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
