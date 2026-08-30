"""Does capping prompt evidence cut latency without costing quality?

§7 asks to reduce latency without reducing safety or quality. The
latency decomposition answered where the time goes:

  mean model calls per request        1.07   (not extra calls)
  correlation(input_tokens, latency)  0.559
  correlation(output_tokens, latency) 0.152

  input tokens    n    p50 latency
     0-249       48       29,281ms
   250-499      120       43,125ms
   750-999       24      103,217ms
  1000-1249      14      139,280ms

ControlPlane makes the SINGLE model call expensive by putting retrieved
evidence in the prompt, and CPU prefill scales with input length.

THE HYPOTHESIS. Retrieval puts all 5 reranked chunks in the prompt, and
the cross-encoder's measured recall@1 on the 26-case relevance set is
1.000 -- the answer-bearing chunk is already first. Chunks 3-5 may be
paid for on every request and used by none.

WHAT IS BEING VARIED, PRECISELY. Only how many chunks reach the MODEL.
Retrieval still fetches 5, adequacy still assesses 5, and grounding is
still judged against the full retrieved set. Evidence serves two
consumers with different needs: the model needs enough context to
answer, the governance layer needs the whole set to judge whether the
corpus covers the question at all. Capping only the first is the point.

WHY THIS CANNOT BY ITSELF SELECT A VALUE FOR k (§62/§66). It runs on
cases drawn from the frozen 62-case benchmark, which is the primary
comparison set. Choosing k from these numbers would be tuning on the
final test set. This is reported as an ABLATION -- it measures the
trade-off; adopting a value requires validation on a separate set, and
the default therefore stays unchanged.

Run (CPU, FAST model, expect 30-60 minutes):
    .venv/Scripts/python -m controlplane.experiments.evaluate_prompt_evidence_budget
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.context import RequestContext
from controlplane.experiments.evaluate_baseline_vs_controlplane import (
    BENCHMARK_MODEL_ROLE,
    _contains_any,
)
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.models.registry import get_configured_provider
from controlplane.runtime import build_default_runtime
from controlplane.state import ExecutionState

_DATASET = Path("data/raw/generated/baseline_vs_controlplane_cases.json")

# Only categories where retrieved evidence is what the answer depends
# on. Capping evidence cannot matter for a public-knowledge question or
# a case designed to be refused.
_EVIDENCE_CATEGORIES = {"GROUNDED_POLICY", "SPECIFIC_THRESHOLD"}
_SUBSET_SIZE = 14

CONDITIONS = {
    "k_all": None,
    "k_3": 3,
    "k_2": 2,
    "k_1": 1,
}


def _load() -> list[dict]:
    with open(_DATASET, encoding="utf-8-sig") as f:
        cases = [c for c in json.load(f) if c.get("category") in _EVIDENCE_CATEGORIES
                 and c.get("expected_values")]
    # Deterministic subset: first N by case_id, so re-runs are comparable.
    return sorted(cases, key=lambda c: c["case_id"])[:_SUBSET_SIZE]


def _run_case(runtime, case: dict) -> dict:
    ctx = RequestContext.new()
    started = time.monotonic()
    failed = False
    answer = None
    try:
        with ctx.bind():
            state = ExecutionState.initial(ctx=ctx, query=case["query"])
            state = runtime.handle(ctx, state)
        answer = state.metadata.get("answer")
        decision = (state.metadata.get("decision") or {}).get("action")
        grounding = None
        for result in state.metadata.get("evaluation_results") or []:
            if result.get("evaluator") == "grounding":
                grounding = result.get("label")
    except Exception as exc:
        failed, decision, grounding = True, f"ERROR: {type(exc).__name__}", None
    latency_ms = int((time.monotonic() - started) * 1000)

    expected = case.get("expected_values") or []
    correct = bool(expected) and answer is not None and _contains_any(answer, expected)

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "correct": correct,
        "answered": bool(answer),
        "grounding": grounding,
        "decision": decision,
        "latency_ms": latency_ms,
        "request_failed": failed,
    }


def _aggregate(rows: list[dict]) -> dict:
    n = len(rows) or 1
    latencies = sorted(r["latency_ms"] for r in rows)
    return {
        "sample_count": len(rows),
        "key_fact_accuracy": sum(1 for r in rows if r["correct"]) / n,
        "answered_rate": sum(1 for r in rows if r["answered"]) / n,
        "grounding_supported_rate": sum(1 for r in rows if r["grounding"] == "SUPPORTED") / n,
        "request_failure_rate": sum(1 for r in rows if r["request_failed"]) / n,
        "latency_ms_mean": sum(latencies) / n,
        "latency_ms_median": latencies[len(latencies) // 2] if latencies else 0,
    }


def main() -> None:
    cases = _load()
    print(f"{len(cases)} evidence-dependent cases: {[c['case_id'] for c in cases]}\n")

    experiment_id = record_experiment(
        experiment_name="prompt_evidence_budget",
        component="generation_prompt",
        algorithm="prompt_evidence_k",
        algorithm_version="v1",
    )

    results, all_rows = {}, {}
    for name, k in CONDITIONS.items():
        print(f"=== {name} (prompt_evidence_k={k}) ===")

        def factory(settings, role=BENCHMARK_MODEL_ROLE):
            return get_configured_provider(settings, role=BENCHMARK_MODEL_ROLE)

        runtime = build_default_runtime(provider_factory=factory, prompt_evidence_k=k)
        rows = []
        for i, case in enumerate(cases, 1):
            row = _run_case(runtime, case)
            rows.append(row)
            print(f"  [{i:>2}/{len(cases)}] {row['case_id']} correct={row['correct']} "
                  f"grounding={row['grounding']} {row['latency_ms']}ms")
        metrics = _aggregate(rows)
        results[name], all_rows[name] = metrics, rows

        run_id = record_run(
            experiment_id=experiment_id, dataset_id="baseline_vs_controlplane_cases",
            dataset_version="v0.1", model=f"role={BENCHMARK_MODEL_ROLE}",
            configuration={"prompt_evidence_k": k},
            notes=f"{len(cases)}-case evidence-dependent subset; ABLATION only, not a tuning run",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)
        print()

    print("=" * 82)
    print(f"{'METRIC':<30}" + "".join(f"{c:>13}" for c in CONDITIONS))
    print("=" * 82)
    for metric in ("key_fact_accuracy", "grounding_supported_rate", "answered_rate",
                   "latency_ms_mean", "latency_ms_median"):
        row = f"{metric:<30}"
        for c in CONDITIONS:
            v = results[c][metric]
            row += f"{v:>13.3f}" if metric.startswith(("key", "ground", "answer")) else f"{v:>13,.0f}"
        print(row)

    baseline = results["k_all"]
    print("\nvs k_all:")
    for c in CONDITIONS:
        if c == "k_all":
            continue
        d_lat = (baseline["latency_ms_mean"] - results[c]["latency_ms_mean"]) / max(baseline["latency_ms_mean"], 1)
        d_acc = results[c]["key_fact_accuracy"] - baseline["key_fact_accuracy"]
        print(f"  {c:<8} latency {d_lat:+.1%}   accuracy {d_acc:+.3f}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"prompt_evidence_budget_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "results": results, "rows": all_rows}, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
