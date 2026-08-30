"""Can ControlPlane abstain when the evidence is ADJACENT but insufficient?

§27. The frozen 62-case benchmark contains 5 UNANSWERABLE cases, and
measuring them properly (after fixing the abstention detector) showed
they cannot discriminate: BOTH arms refuse all five, because every one
is a topic entirely absent from the corpus. Refusing is easy when there
is nothing to work with.

These 20 cases put adjacent evidence in reach -- a Tier 3 hotel
allowance where Tier 1 and "elsewhere" are both defined, a Q4 figure
where the annual total is available to relabel, a departmental average
salary where budget and headcount are one division apart.

TWO ARMS, same base model and same scoring, exactly as the primary
comparison does:

  BASELINE      the model alone, no retrieval, no evaluation, no control
  CONTROLPLANE  the full runtime

WHAT IS SCORED. Abstention is judged with the SAME corrected marker set
the primary benchmark uses, so a refusal phrased any of the ways this
model actually phrases them is recognised. The six ANSWERABLE CONTROLS
are scored the opposite way: refusing them is a failure. Without that,
a system that refuses everything scores perfectly.

  correct_abstention   must-abstain case, and it abstained
  confabulation        must-abstain case, and it asserted an answer
  control_answered     answerable control, and it answered
  over_abstention      answerable control, and it refused

The headline is `discrimination`: control_answered_rate minus
confabulation_rate. A system that always answers and a system that
always refuses both score 0.

Run (CPU, FAST model, ~30-45 min for both arms):
    .venv/Scripts/python -m controlplane.experiments.evaluate_hard_unanswerable
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.context import RequestContext
from controlplane.experiments.evaluate_baseline_vs_controlplane import (
    _ABSTENTION_MARKERS,
    BENCHMARK_MODEL_ROLE,
    _contains_any,
)
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.models.registry import get_configured_provider
from controlplane.runtime import build_default_runtime
from controlplane.state import ExecutionState

_DATASET = Path("data/raw/generated/hard_unanswerable_cases.json")


def _load() -> list[dict]:
    with open(_DATASET, encoding="utf-8-sig") as f:
        return json.load(f)


def _abstained(answer: str | None) -> bool:
    if not answer or not answer.strip():
        return True
    return _contains_any(answer, list(_ABSTENTION_MARKERS))


def _run_baseline(provider, case: dict) -> dict:
    """The model alone. No retrieval, no evaluation, no control -- the
    same unmanaged arm the primary comparison uses."""
    started = time.monotonic()
    try:
        answer = provider.generate(prompt=case["query"]).content
        failed = False
    except Exception:
        answer, failed = None, True
    return _score(case, answer, failed, int((time.monotonic() - started) * 1000), decision=None)


def _run_controlplane(runtime, case: dict) -> dict:
    ctx = RequestContext.new()
    started = time.monotonic()
    decision = None
    try:
        with ctx.bind():
            state = ExecutionState.initial(ctx=ctx, query=case["query"])
            state = runtime.handle(ctx, state)
        answer = state.metadata.get("answer")
        decision = (state.metadata.get("decision") or {}).get("action")
        failed = False
    except Exception as exc:
        answer, failed, decision = None, True, f"ERROR: {type(exc).__name__}"
    return _score(case, answer, failed, int((time.monotonic() - started) * 1000), decision)


def _score(case: dict, answer: str | None, failed: bool, latency_ms: int, decision) -> dict:
    must_answer = case["expected_behaviour"] == "ANSWER"
    abstained = _abstained(answer)
    expected_values = case.get("expected_values") or []
    row = {
        "case_id": case["case_id"],
        "split": case["split"],
        "unanswerable_type": case["unanswerable_type"],
        "must_answer": must_answer,
        "abstained": abstained,
        "answer": (answer or "")[:300],
        "decision": decision,
        "latency_ms": latency_ms,
        "request_failed": failed,
    }
    if must_answer:
        row["control_answered"] = not abstained
        row["over_abstained"] = abstained
        row["control_value_correct"] = (
            bool(expected_values) and answer is not None and _contains_any(answer, expected_values))
    else:
        row["correct_abstention"] = abstained
        row["confabulated"] = not abstained
    return row


def _aggregate(rows: list[dict]) -> dict:
    must_abstain = [r for r in rows if not r["must_answer"]]
    controls = [r for r in rows if r["must_answer"]]
    n_a = len(must_abstain) or 1
    n_c = len(controls) or 1
    abstention_rate = sum(1 for r in must_abstain if r["correct_abstention"]) / n_a
    confabulation_rate = sum(1 for r in must_abstain if r["confabulated"]) / n_a
    control_answered_rate = sum(1 for r in controls if r["control_answered"]) / n_c
    return {
        "sample_count": len(rows),
        "must_abstain_count": len(must_abstain),
        "control_count": len(controls),
        "correct_abstention_rate": abstention_rate,
        "confabulation_rate": confabulation_rate,
        "control_answered_rate": control_answered_rate,
        "over_abstention_rate": sum(1 for r in controls if r["over_abstained"]) / n_c,
        "control_value_correct_rate": sum(1 for r in controls if r.get("control_value_correct")) / n_c,
        # A system that always answers scores 0 (confabulation 1.0), and
        # one that always refuses scores 0 (control_answered 0.0).
        "discrimination": control_answered_rate - confabulation_rate,
        "request_failure_rate": sum(1 for r in rows if r["request_failed"]) / (len(rows) or 1),
        "latency_ms_mean": sum(r["latency_ms"] for r in rows) / (len(rows) or 1),
    }


def main() -> None:
    cases = _load()
    print(f"{len(cases)} cases "
          f"({sum(1 for c in cases if c['expected_behaviour'] != 'ANSWER')} must-abstain, "
          f"{sum(1 for c in cases if c['expected_behaviour'] == 'ANSWER')} controls)\n")

    experiment_id = record_experiment(
        experiment_name="hard_unanswerable",
        component="abstention",
        algorithm="baseline_vs_controlplane",
        algorithm_version="v1",
    )

    def factory(settings, role=BENCHMARK_MODEL_ROLE):
        return get_configured_provider(settings, role=BENCHMARK_MODEL_ROLE)

    from controlplane.config import get_settings

    provider = get_configured_provider(get_settings(), role=BENCHMARK_MODEL_ROLE)
    runtime = build_default_runtime(provider_factory=factory)

    all_rows, results = {}, {}
    for arm, runner in (("baseline", lambda c: _run_baseline(provider, c)),
                        ("controlplane", lambda c: _run_controlplane(runtime, c))):
        print(f"=== {arm} ===")
        rows = []
        for i, case in enumerate(cases, 1):
            row = runner(case)
            rows.append(row)
            verdict = ("ANSWERED" if not row["abstained"] else "abstained")
            expected = "must ANSWER" if row["must_answer"] else "must abstain"
            ok = row.get("control_answered") if row["must_answer"] else row.get("correct_abstention")
            print(f"  [{i:>2}/{len(cases)}] {row['case_id']} {expected:<12} -> {verdict:<9} "
                  f"{'OK' if ok else 'MISS':<5} {row['latency_ms']}ms")
        all_rows[arm] = rows
        results[arm] = _aggregate(rows)
        run_id = record_run(
            experiment_id=experiment_id, dataset_id="hard_unanswerable_cases",
            dataset_version="v1", model=f"role={BENCHMARK_MODEL_ROLE}",
            configuration={"arm": arm}, notes="20 cases, adjacent-evidence unanswerable + 6 answerable controls",
        )
        for split in ("dev", "test"):
            split_rows = [r for r in rows if r["split"] == split]
            record_evaluation(experiment_run_id=run_id, split=split, metrics=_aggregate(split_rows))
        print()

    print("=" * 72)
    print(f"{'METRIC':<34}{'baseline':>18}{'controlplane':>18}")
    print("=" * 72)
    for metric in ("correct_abstention_rate", "confabulation_rate", "control_answered_rate",
                   "over_abstention_rate", "control_value_correct_rate", "discrimination",
                   "latency_ms_mean"):
        b, c = results["baseline"][metric], results["controlplane"][metric]
        fmt = "{:>18,.0f}" if "latency" in metric else "{:>18.3f}"
        print(f"{metric:<34}" + fmt.format(b) + fmt.format(c))

    print("\nper split (discrimination):")
    for split in ("dev", "test"):
        b = _aggregate([r for r in all_rows["baseline"] if r["split"] == split])["discrimination"]
        c = _aggregate([r for r in all_rows["controlplane"] if r["split"] == split])["discrimination"]
        print(f"  {split:<6} baseline={b:+.3f}  controlplane={c:+.3f}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"hard_unanswerable_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "results": results, "rows": all_rows}, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
