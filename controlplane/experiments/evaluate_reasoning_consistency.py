"""Can the reasoning evaluator be improved without adding keywords?

Spec §37. The shipped ``ReasoningEvaluator`` is a fixed list of adjacent
polarity phrases; expanding the dataset from 12 to 24 cases measured its
real recall at 0.167. §37 explicitly forbids the easy response ("do not
fix it by adding more keyword rules") and names the alternatives:
numeric consistency, claim extraction, entailment, scope.

FOUR CONDITIONS:

  A_current       The shipped adjacent-polarity-pair list. Baseline.
  B_numeric       Deterministic numeric-consistency check only.
  C_entailment    google/flan-t5-base zero-shot contradiction only.
  D_numeric_nli   Both, OR-combined.

SPLITS (§66). Tuning and inspection happen on ``reasoning_cases_dev``
(24 cases, authored for this experiment). ``reasoning_cases`` (24 cases,
which predate it) is the held-out TEST set and is scored once per
condition. The dev split is deliberately majority NOT_CONTRADICTORY,
because the way a contradiction detector actually fails in production is
by flagging correctly-scoped answers -- "vendors are not paid before
delivery, but prepayment is permitted for contracts under $2,000" is
consistent, and both a polarity check and an off-the-shelf NLI model
call it a contradiction.

METRICS. Macro-F1 over both labels, plus per-class precision/recall,
because accuracy alone hides the exact trade that matters: a detector
that flags everything gets perfect recall on contradictions and is
useless.

RAM: flan-t5-base is ~1GB on CPU, loaded once. Do not run this
concurrently with a 7B judge.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_reasoning_consistency
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.evaluation.reasoning_consistency import (
    check_entailment_consistency,
    check_numeric_consistency,
)
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

CONTRADICTORY = "SELF_CONTRADICTORY"
CONSISTENT = "NO_CONTRADICTION_DETECTED"

_DEV = Path("data/raw/generated/reasoning_cases_dev.json")
_TEST = Path("data/raw/generated/reasoning_cases.json")

CONDITIONS = ("A_current", "B_numeric", "C_entailment", "D_numeric_nli")


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _predict_current(answer: str) -> tuple[str, list[str]]:
    from controlplane.evaluation.evaluators import _CONTRADICTION_PAIRS

    lowered = answer.lower()
    hits = [f"{pos!r}+{neg!r}" for pos, neg in _CONTRADICTION_PAIRS if pos in lowered and neg in lowered]
    return (CONTRADICTORY if hits else CONSISTENT), hits


def _predict(condition: str, answer: str) -> tuple[str, list[str]]:
    if condition == "A_current":
        return _predict_current(answer)
    findings = []
    if condition in ("B_numeric", "D_numeric_nli"):
        findings += check_numeric_consistency(answer)
    if condition in ("C_entailment", "D_numeric_nli"):
        findings += check_entailment_consistency(answer)
    label = CONTRADICTORY if findings else CONSISTENT
    return label, [f"{f.kind}: {f.detail}" for f in findings]


def _metrics(rows: list[dict]) -> dict:
    def prf(pos: str) -> tuple[float, float, float]:
        tp = sum(1 for r in rows if r["predicted"] == pos and r["expected"] == pos)
        fp = sum(1 for r in rows if r["predicted"] == pos and r["expected"] != pos)
        fn = sum(1 for r in rows if r["predicted"] != pos and r["expected"] == pos)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return p, r, (2 * p * r / (p + r) if p + r else 0.0)

    cp, cr, cf = prf(CONTRADICTORY)
    np_, nr, nf = prf(CONSISTENT)
    n = len(rows)
    return {
        "n": n,
        "accuracy": sum(1 for r in rows if r["predicted"] == r["expected"]) / n if n else 0.0,
        "contradiction_precision": cp,
        "contradiction_recall": cr,
        "contradiction_f1": cf,
        "consistent_f1": nf,
        "macro_f1": (cf + nf) / 2,
        "false_positives": sum(1 for r in rows if r["predicted"] == CONTRADICTORY and r["expected"] != CONTRADICTORY),
        "false_negatives": sum(1 for r in rows if r["predicted"] != CONTRADICTORY and r["expected"] == CONTRADICTORY),
        "mean_latency_ms": sum(r["latency_ms"] for r in rows) / n if n else 0.0,
    }


def main(conditions: tuple[str, ...] = CONDITIONS) -> None:
    splits = {"dev": _load(_DEV), "test": _load(_TEST)}
    print(f"dev: {len(splits['dev'])}   test (held out): {len(splits['test'])}\n")

    experiment_id = record_experiment(
        experiment_name="reasoning_consistency",
        component="reasoning_evaluator",
        algorithm="polarity_vs_numeric_vs_entailment",
        algorithm_version="v2",
    )

    results: dict = {}
    detail: dict = {}
    for condition in conditions:
        results[condition] = {}
        detail[condition] = {}
        for split_name, cases in splits.items():
            rows = []
            for case in cases:
                started = time.monotonic()
                predicted, why = _predict(condition, case["answer"])
                rows.append({
                    "case_id": case["case_id"],
                    "category": case.get("category"),
                    "expected": case["expected_label"],
                    "predicted": predicted,
                    "why": why,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                })
            results[condition][split_name] = _metrics(rows)
            detail[condition][split_name] = rows
        run_id = record_run(
            experiment_id=experiment_id, dataset_id="reasoning_cases",
            dataset_version="v2", model="flan-t5-base" if "entail" in condition or "nli" in condition else "deterministic",
            configuration={"condition": condition}, notes="24 dev + 24 held-out test; CPU",
        )
        for split_name in splits:
            record_evaluation(experiment_run_id=run_id, split=split_name, metrics=results[condition][split_name])
        print(f"  {condition} done")

    print("\n" + "=" * 92)
    print(f"{'METRIC':<32}" + "".join(f"{c[:14]:>15}" for c in conditions))
    print("=" * 92)
    for split_name in ("dev", "test"):
        print(f"-- {split_name} --")
        for metric in ("accuracy", "macro_f1", "contradiction_recall", "contradiction_precision",
                       "false_positives", "false_negatives", "mean_latency_ms"):
            row = f"  {metric:<30}"
            for c in conditions:
                v = results[c][split_name][metric]
                row += f"{v:>15.3f}" if isinstance(v, float) else f"{v:>15}"
            print(row)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if set(conditions) == set(CONDITIONS) else "_" + "-".join(c[0] for c in conditions)
    out_path = out_dir / f"reasoning_consistency_{date.today().isoformat()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "results": results, "detail": detail}, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    import sys

    # Allows running only the deterministic conditions when a heavier
    # job already holds RAM (§62) -- the model conditions can then be
    # scored later without redoing the free ones.
    selected = tuple(c for c in CONDITIONS if not sys.argv[1:] or c in sys.argv[1:])
    main(selected)
