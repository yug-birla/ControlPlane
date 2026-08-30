"""Does giving numeric claims a PROVENANCE reduce over-control?

Spec §8. The 62-case benchmark measured 30.4% benign over-control, and
the dashboard's attribution (counted from recorded per-case
``flagged_evaluators``) put ``factuality`` at the top: 8 of the 14
withheld benign cases.

Reading those 8 showed a single mechanism. The evaluator treats every
number in the answer as a claim needing evidential support, so the
unmatched number was usually the one the USER PUT IN THEIR OWN QUESTION:

  BVC-060  "an expense of $12,000 falls in the $5,001-$25,000 band and
            requires department director approval"   -- CORRECT, flagged
            because 12,000 appears in no document.
  BVC-061  "99.85% is below the 99.9% guarantee"     -- CORRECT, flagged
            for restating the figure it was asked about.
  BVC-062  "$120,000 exceeds the $100k threshold"    -- CORRECT, same.

Root cause class: ALGORITHM. A number has provenance -- it can come from
the evidence, from the question, or from arithmetic over those. Only a
number with none of those origins is an unsupported claim. This is not
an exception list; it is the missing distinction.

CONDITIONS:

  A_current       every answer number must appear literally in evidence
  B_query_exempt  numbers supplied by the user's question are not
                  fabrications
  C_query_derived B, plus numbers reachable by ONE arithmetic step over
                  evidence/query values ("at $250/night, three nights
                  cost $750" invents nothing)

THE GUARD THAT MATTERS MOST. FA-D07 and FA-T08 put a legitimate query
number and a fabricated threshold in the SAME answer. Excusing the first
must not excuse the second, or this "fix" would simply switch the
detector off. The derived-number check is restricted to one operation
over a pair of values for the same reason -- longer chains would
eventually make almost any number derivable.

SPLITS (§62). FA-D* is dev and was inspected freely; FA-T* is held out
and scored once per condition.

Run (deterministic, no model, seconds):
    .venv/Scripts/python -m controlplane.experiments.evaluate_factuality_provenance
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.evaluation.evaluators import EvaluationContext, FactualityEvaluator
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_CASES = Path("data/raw/generated/factuality_cases.json")

CONDITIONS = {
    "A_current": {"exempt_query_numbers": False, "allow_derived_numbers": False},
    "B_query_exempt": {"exempt_query_numbers": True, "allow_derived_numbers": False},
    "C_query_derived": {"exempt_query_numbers": True, "allow_derived_numbers": True},
}

# A control event is triggered by anything other than a clean SUPPORTED
# or an honest NOT_APPLICABLE. That is the property §8 is about, so it
# is measured directly rather than inferred from the label distribution.
_CONTROLLING = {"PARTIALLY_SUPPORTED", "CONTRADICTED"}


def _load(split: str) -> list[dict]:
    with open(_CASES, encoding="utf-8-sig") as f:
        return [c for c in json.load(f) if c["split"] == split]


def _metrics(rows: list[dict]) -> dict:
    n = len(rows) or 1
    should_pass = [r for r in rows if r["expected"] not in _CONTROLLING]
    should_flag = [r for r in rows if r["expected"] in _CONTROLLING]
    over = [r for r in should_pass if r["predicted"] in _CONTROLLING]
    under = [r for r in should_flag if r["predicted"] not in _CONTROLLING]
    return {
        "sample_count": len(rows),
        "exact_label_accuracy": sum(1 for r in rows if r["predicted"] == r["expected"]) / n,
        "control_decision_accuracy": sum(
            1 for r in rows if (r["predicted"] in _CONTROLLING) == (r["expected"] in _CONTROLLING)
        ) / n,
        "over_control_count": len(over),
        # AUDIT (SS53): an empty denominator must not read as perfect.
        # `x / (len(s) or 1)` returns 0.0 when s is empty, so a split
        # containing no cases of a kind reports a 0.0 failure rate for it --
        # indistinguishable from having tested it and passed. The rate is
        # undefined there, and None says so; the count beside it stays 0.
        "over_control_rate": (
            len(over) / len(should_pass) if should_pass else None),
        "missed_fabrication_count": len(under),
        "missed_fabrication_rate": (
            len(under) / len(should_flag) if should_flag else None),
        "over_controlled_cases": [r["case_id"] for r in over],
        "missed_cases": [r["case_id"] for r in under],
    }


def main() -> None:
    splits = {"dev": _load("dev"), "test": _load("test")}
    print(f"dev: {len(splits['dev'])}   test (held out): {len(splits['test'])}\n")

    experiment_id = record_experiment(
        experiment_name="factuality_numeric_provenance",
        component="factuality_evaluator",
        algorithm="literal_match_vs_claim_provenance",
        algorithm_version="v2",
    )

    results: dict = {}
    detail: dict = {}
    for name, cfg in CONDITIONS.items():
        evaluator = FactualityEvaluator(**cfg)
        results[name] = {}
        detail[name] = {}
        for split_name, cases in splits.items():
            rows = []
            for case in cases:
                result = evaluator.evaluate(EvaluationContext(
                    query=case["query"], answer=case["answer"],
                    evidence_texts=case["evidence"], sql_rows=[],
                ))
                rows.append({
                    "case_id": case["case_id"], "category": case["category"],
                    "expected": case["expected_label"], "predicted": result.label,
                    "unmatched": result.evidence.get("unmatched"),
                    "query_sourced": result.evidence.get("query_sourced"),
                    "derived": result.evidence.get("derived"),
                })
            results[name][split_name] = _metrics(rows)
            detail[name][split_name] = rows

        run_id = record_run(
            experiment_id=experiment_id, dataset_id="factuality_cases",
            dataset_version="v1", model="deterministic",
            configuration=cfg, notes="24 hand-authored cases, dev/test split; no model",
        )
        for split_name in splits:
            record_evaluation(experiment_run_id=run_id, split=split_name, metrics={
                k: v for k, v in results[name][split_name].items() if not isinstance(v, list)
            })

    print("=" * 82)
    print(f"{'METRIC':<34}" + "".join(f"{c[:14]:>16}" for c in CONDITIONS))
    print("=" * 82)
    for split_name in ("dev", "test"):
        print(f"-- {split_name} --")
        for metric in ("exact_label_accuracy", "control_decision_accuracy",
                       "over_control_count", "missed_fabrication_count"):
            row = f"  {metric:<32}"
            for c in CONDITIONS:
                v = results[c][split_name][metric]
                row += f"{v:>16.3f}" if isinstance(v, float) else f"{v:>16}"
            print(row)
    for c in CONDITIONS:
        print(f"\n{c}: test over-controlled={results[c]['test']['over_controlled_cases']} "
              f"missed={results[c]['test']['missed_cases']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"factuality_provenance_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "results": results, "detail": detail}, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
