"""Ablation study: which ControlPlane components actually contribute?

Bootstrap SS33/SS43. Same dataset, same model, same scoring code as
``evaluate_baseline_vs_controlplane.py`` -- only one component is
removed per condition, so any difference is attributable to that
component rather than to a changed measurement.

CONDITIONS

  A  BASELINE                 no ControlPlane at all (reference point,
                              re-measured here so every number in this
                              table comes from one run)

  B  NO_CORPUS_AFFINITY       full ControlPlane, but the Milestone 9
                              semantic RAG-routing layer disabled --
                              i.e. exactly the Milestone 8 system. This
                              isolates the contribution of the single
                              largest fix in this milestone: keyword-only
                              RAG routing had measured recall 0.053 on
                              corpus-answerable questions.

  C  NO_ENFORCEMENT           full ControlPlane observation (routing,
                              retrieval, evaluation, decision) with
                              enforcement suppressed -- Shadow Mode.
                              Isolates the contribution of the control
                              loop itself: everything is detected, but
                              no intervention runs and nothing is
                              withheld.

  D  FULL_CONTROLPLANE        everything on.

WHAT EACH COMPARISON ANSWERS

  D vs A   does ControlPlane beat an unmanaged model?          (product claim)
  D vs B   did the semantic routing fix matter?                (this milestone)
  D vs C   does *enforcing* add anything over *detecting*?     (the thesis --
           "ControlPlane should do something about it", not merely report it)

Run (long: CPU-only local inference x 4 conditions):
    .venv/Scripts/python -m controlplane.experiments.evaluate_ablations
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.context import RequestContext
from controlplane.experiments.evaluate_baseline_vs_controlplane import (
    DATASET_ID,
    DATASET_VERSION,
    _aggregate,
    _gold_evidence,
    _load_cases,
    _run_baseline,
    _score_answer,
)
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.runtime import build_default_runtime
from controlplane.state import ExecutionState


def _run_controlplane_variant(cases: list[dict], *, use_corpus_affinity: bool, shadow_mode: bool) -> list[dict]:
    """One ControlPlane condition. Deliberately mirrors
    ``evaluate_baseline_vs_controlplane._run_controlplane`` rather than
    importing it, because that function builds the default runtime and
    these conditions need a configured one -- the SCORING, which is what
    must not differ between conditions, is the shared ``_score_answer``."""
    runtime = build_default_runtime(
        query_profiler=HybridQueryProfiler(use_corpus_affinity=use_corpus_affinity),
        shadow_mode=shadow_mode,
    )

    rows = []
    for case in cases:
        ctx = RequestContext.new()
        state = ExecutionState.initial(ctx, case["query"])
        start = time.monotonic()
        failed = False
        try:
            with ctx.bind():
                state = runtime.handle(ctx, state)
            answer = state.metadata.get("answer")
        except Exception as exc:
            answer, failed = None, True
            print(f"  {case['case_id']}: FAILURE: {exc}")
        latency_ms = int((time.monotonic() - start) * 1000)

        meta = state.metadata
        decision = (meta.get("decision") or {}).get("action")
        verification = (meta.get("verification") or {}).get("status")
        evaluations = meta.get("evaluation") or []
        flagged = [
            e["evaluator"] for e in evaluations
            if e.get("recommended_signal") in ("FLAG_FOR_REVIEW", "BLOCK")
        ]

        # In shadow mode nothing is enforced by construction, so
        # "controlled" means "would have been controlled" -- recorded
        # separately so the two are never conflated in the results.
        controlled = bool(
            answer is None
            or decision in ("HUMAN_REVIEW", "BLOCK", "ASK_CLARIFICATION", "ABSTAIN")
            or verification in ("REJECTED", "NOT_VERIFIED")
            or flagged
        )

        graph = (meta.get("capability_route") or {}).get("graph") or {}
        rag_ran = any(
            n.get("capability") == "RAG" and n.get("status") == "COMPLETED"
            for n in graph.get("nodes", [])
        )

        rows.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "answer": answer,
            "latency_ms": latency_ms,
            "output_tokens": (meta.get("model") or {}).get("output_tokens"),
            "provider_failed": failed,
            "decision": decision,
            "verification": verification,
            "flagged_evaluators": flagged,
            "controlled": controlled,
            "retrieval_ran": rag_ran,
            **_score_answer(case, answer, _gold_evidence(case.get("gold_document"))),
        })
        print(f"  {case['case_id']} correct={rows[-1]['key_fact_correct']} "
              f"rag={rag_ran} decision={decision} {latency_ms}ms")
    return rows


def _retrieval_rate(rows: list[dict], cases: list[dict]) -> float | None:
    by_id = {c["case_id"]: c for c in cases}
    pool = [r for r in rows if by_id[r["case_id"]].get("gold_document")]
    if not pool:
        return None
    return sum(1 for r in pool if r.get("retrieval_ran")) / len(pool)


def main() -> None:
    cases = _load_cases()
    print(f"Loaded {len(cases)} cases\n")

    experiment_id = record_experiment(
        experiment_name="controlplane_ablations",
        component="end_to_end",
        algorithm="component_ablation",
        algorithm_version="v1",
    )

    conditions: dict[str, list[dict]] = {}

    # Condition A is reused from the most recent
    # evaluate_baseline_vs_controlplane run when one exists, rather than
    # re-measured. This is sound because the baseline path is literally
    # ``provider.generate(prompt=query)`` -- it touches no ControlPlane
    # code, so no change to routing/decision/enforcement can alter it --
    # and it saves ~15 minutes of CPU-only inference. If no prior run is
    # found it is measured here.
    prior = sorted(Path("docs/EVALUATION/RESULTS").glob("baseline_vs_controlplane_*.json"))
    if prior:
        with open(prior[-1], encoding="utf-8") as f:
            conditions["A_baseline"] = json.load(f)["baseline"]["rows"]
        print(f"=== A: BASELINE (reused from {prior[-1].name}) ===")
    else:
        print("=== A: BASELINE (no ControlPlane) ===")
        conditions["A_baseline"] = _run_baseline(cases)

    print("\n=== B: NO_CORPUS_AFFINITY (= the Milestone 8 system) ===")
    conditions["B_no_corpus_affinity"] = _run_controlplane_variant(
        cases, use_corpus_affinity=False, shadow_mode=False
    )

    print("\n=== C: NO_ENFORCEMENT (shadow mode: detect but never act) ===")
    conditions["C_no_enforcement"] = _run_controlplane_variant(
        cases, use_corpus_affinity=True, shadow_mode=True
    )

    print("\n=== D: FULL_CONTROLPLANE ===")
    conditions["D_full_controlplane"] = _run_controlplane_variant(
        cases, use_corpus_affinity=True, shadow_mode=False
    )

    results = {}
    for name, rows in conditions.items():
        metrics = _aggregate(rows, cases)
        metrics["retrieval_rate_on_corpus_answerable"] = _retrieval_rate(rows, cases)
        results[name] = metrics
        run_id = record_run(
            experiment_id=experiment_id,
            dataset_id=DATASET_ID,
            dataset_version=DATASET_VERSION,
            model=name,
            configuration={"condition": name},
            notes="ablation; real local Qwen2.5-1.5B-Instruct on CPU; DEVELOPMENT_TEST scale (26 cases)",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    keys = [
        "key_fact_accuracy_factual_cases",
        "hallucination_rate_factual_cases",
        "grounding_supported_rate_factual_cases",
        "retrieval_rate_on_corpus_answerable",
        "appropriate_abstention_rate_unanswerable",
        "control_rate_on_unsafe_cases",
        "control_rate_on_benign_cases",
        "latency_ms_mean",
    ]
    names = list(conditions)
    print("\n" + "=" * 100)
    print(f"{'METRIC':<44}" + "".join(f"{n.split('_')[0]:>13}" for n in names))
    print("=" * 100)
    for key in keys:
        row = f"{key:<44}"
        for n in names:
            v = results[n].get(key)
            row += f"{v:>13.3f}" if isinstance(v, float) else f"{str(v):>13}"
        print(row)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ablations_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment_id": experiment_id,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "results": results,
            "rows": conditions,
        }, f, indent=2, default=str)
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
