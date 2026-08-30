"""What does a FALSE action actually cost?

`evaluate_actionability_escalation` established the trade. On held-out
data the shipped profiler misses 47.6% of real actions (11 of 21
caught); escalating when any one of the k neighbours is agentic catches
90.5% (19 of 21) but raises the false-action rate from 0.035 to 0.237.

Whether that is a good trade cannot be settled by staring at the two
numbers, because they are not in the same units. A missed action removes
agent governance from a request that needed it. A false action adds
something -- but WHAT it adds is an empirical question about the rest of
the pipeline, and it has never been measured.

The chain under test:

    actionability -> intent -> risk severity -> policy tier
                  -> CapabilityHint.AGENT -> actor node -> AgentGate

So a false action is only expensive if it actually changes the policy
tier or adds control to a benign request. If the risk profiler is doing
its own work and a mislabelled lookup still lands in the same tier, the
cost is one graph node.

WHAT IS MEASURED, on the same held-out splits, for both conditions:

  tier_changed_rate       non-agentic queries whose POLICY TIER rose
  escalated_to_review     non-agentic queries reaching a tier that
                          demands human review
  agent_node_added_rate   non-agentic queries that gained an actor node
  recovered_review        genuinely agentic queries that reached review
                          under the candidate but not under the current
                          profiler -- the benefit side, in the same units

Embeddings and rules only. No generation, no judge, no RAM contention.

    .venv/Scripts/python -m controlplane.experiments.evaluate_escalation_cost
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.policy.baseline import PolicyBaseline
from controlplane.query_intelligence.fingerprint import CapabilityHint
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler

DATASET_ID = "query_profiles"
DATASET_VERSION = "v0.1"
HELD_OUT = ("validation", "test", "challenge")

# Tiers that impose real cost on the user rather than just bookkeeping.
_REVIEW_TIERS = {"HIGH_RISK", "CRITICAL_ACTION"}


def _load(split: str) -> list[dict]:
    with open(Path(f"data/evaluation/{split}/query_profiles_{split}.json"), encoding="utf-8-sig") as f:
        return json.load(f)


def _trace(profiler, records: list[dict]) -> list[dict]:
    risk_profiler, policy = BaselineRiskProfiler(), PolicyBaseline()
    rows = []
    for record in records:
        fingerprint = profiler.profile(record["query"])
        risk = risk_profiler.profile(record["query"], fingerprint)
        decision = policy.decide(risk.severity)
        rows.append({
            "query": record["query"],
            "gold_agentic": record["actionability"] == "agentic",
            "predicted_agentic": fingerprint.actionability.value == "agentic",
            "intent": fingerprint.intent.value,
            "severity": risk.severity.value,
            "tier": decision.tier.value,
            "agent_node": CapabilityHint.AGENT in fingerprint.capability_hints,
        })
    return rows


def _compare(current: list[dict], candidate: list[dict]) -> dict:
    non_agentic = [i for i, r in enumerate(current) if not r["gold_agentic"]]
    agentic = [i for i, r in enumerate(current) if r["gold_agentic"]]
    n_non, n_ag = len(non_agentic) or 1, len(agentic) or 1

    tier_changed = [i for i in non_agentic if current[i]["tier"] != candidate[i]["tier"]]
    to_review = [
        i for i in non_agentic
        if candidate[i]["tier"] in _REVIEW_TIERS and current[i]["tier"] not in _REVIEW_TIERS
    ]
    node_added = [
        i for i in non_agentic if candidate[i]["agent_node"] and not current[i]["agent_node"]
    ]
    recovered = [
        i for i in agentic
        if candidate[i]["predicted_agentic"] and not current[i]["predicted_agentic"]
    ]
    recovered_review = [
        i for i in agentic
        if candidate[i]["tier"] in _REVIEW_TIERS and current[i]["tier"] not in _REVIEW_TIERS
    ]
    return {
        "non_agentic_count": len(non_agentic),
        "agentic_count": len(agentic),
        "tier_changed_count": len(tier_changed),
        "tier_changed_rate": len(tier_changed) / n_non,
        "escalated_to_review_count": len(to_review),
        "escalated_to_review_rate": len(to_review) / n_non,
        "agent_node_added_count": len(node_added),
        "agent_node_added_rate": len(node_added) / n_non,
        "actions_recovered_count": len(recovered),
        "actions_recovered_rate": len(recovered) / n_ag,
        "recovered_into_review_count": len(recovered_review),
        "tier_shift": _tier_shift(current, candidate, non_agentic),
    }


def _tier_shift(current, candidate, indices) -> dict:
    shift: dict[str, int] = {}
    for i in indices:
        if current[i]["tier"] != candidate[i]["tier"]:
            key = f"{current[i]['tier']} -> {candidate[i]['tier']}"
            shift[key] = shift.get(key, 0) + 1
    return shift


def main() -> None:
    experiment_id = record_experiment(
        experiment_name="escalation_downstream_cost",
        component="query_profiler",
        algorithm="agentic_escalation_cost",
        algorithm_version="v1",
    )

    # Both arms pinned; see B18 -- a control arm that follows the shipped
    # default stops being a control the moment the default moves.
    current = HybridQueryProfiler(agentic_escalation_threshold=None)
    candidate = HybridQueryProfiler(agentic_escalation_threshold=0.01)  # B: any of k

    all_current, all_candidate, per_split = [], [], {}
    for split in HELD_OUT:
        records = _load(split)
        rows_current = _trace(current, records)
        rows_candidate = _trace(candidate, records)
        all_current += rows_current
        all_candidate += rows_candidate
        per_split[split] = _compare(rows_current, rows_candidate)
        print(f"{split}: {per_split[split]['tier_changed_count']} tier changes among "
              f"{per_split[split]['non_agentic_count']} non-agentic queries")

    pooled = _compare(all_current, all_candidate)

    print("\n" + "=" * 78)
    print("DOWNSTREAM COST OF THE 1-of-k ESCALATION (held-out, pooled)")
    print("=" * 78)
    print(f"non-agentic queries                   {pooled['non_agentic_count']}")
    print(f"  policy tier changed                 {pooled['tier_changed_count']:>4}  "
          f"({pooled['tier_changed_rate']:.3f})")
    print(f"  newly requires human review         {pooled['escalated_to_review_count']:>4}  "
          f"({pooled['escalated_to_review_rate']:.3f})")
    print(f"  gained an actor agent node          {pooled['agent_node_added_count']:>4}  "
          f"({pooled['agent_node_added_rate']:.3f})")
    print(f"\ngenuinely agentic queries             {pooled['agentic_count']}")
    print(f"  actions now recognised              {pooled['actions_recovered_count']:>4}  "
          f"({pooled['actions_recovered_rate']:.3f})")
    print(f"  now reaching human review           {pooled['recovered_into_review_count']:>4}")
    print(f"\ntier shifts among non-agentic queries: {pooled['tier_shift'] or 'none'}")

    run_id = record_run(
        experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
        model="all-MiniLM-L6-v2", configuration={"candidate": "any_of_k", "tau": 0.01},
        notes="downstream policy-tier cost of actionability escalation",
    )
    for split, metrics in per_split.items():
        record_evaluation(experiment_run_id=run_id, split=split,
                          metrics={k: v for k, v in metrics.items() if k != "tier_shift"})
    record_evaluation(experiment_run_id=run_id, split="held_out_pooled",
                      metrics={k: v for k, v in pooled.items() if k != "tier_shift"})

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"escalation_cost_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "per_split": per_split,
                   "held_out_pooled": pooled}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
