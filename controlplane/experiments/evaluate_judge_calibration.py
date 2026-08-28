"""Judge calibration -- deterministic lexical baseline vs Local Judge vs
Remote Judge (Gemini), on the same constructed grounding benchmark, per
bootstrap SS15/43: "LLM judges are NOT ground truth... measure
agreement... if disagreement is high, do not blindly use the judge as
truth."

Ground truth construction (DERIVED, not organic -- no real
grounding-labeled dataset with (query, evidence, answer, SUPPORTED/
UNSUPPORTED) triples exists in this repo): built from
``data/raw/generated/rag_cases.json``'s SUFFICIENT-labeled records.
- SUPPORTED cases: a record's own (query, documents-as-evidence,
  expected_answer) -- ``expected_answer`` is genuinely drawn from that
  record's evidence, so this is a real positive.
- UNSUPPORTED cases: one record's (query, evidence) paired with a
  DIFFERENT, unrelated record's ``expected_answer`` -- necessarily
  off-topic, so this is a real (constructed) negative.
No PARTIALLY_SUPPORTED ground-truth cases are constructed this way (the
construction method can't produce a genuinely "partial" case); each
scorer's own PARTIALLY_SUPPORTED output is scored as UNSUPPORTED for
this binary comparison, and the raw 3-way label distribution is reported
separately so that collapsing isn't hiding anything.

SMOKE_TEST scale (bootstrap SS40): 20 cases (10 per class), because the
Local Judge is real but slow -- measured 30-90s per call on this
CPU-only machine (see docs/EVALUATION/EVALUATOR_RESULTS.md). Remote
Judge (Gemini) is skipped with an explicit NOT_MEASURED reason if no
GEMINI_API_KEY_1/2 is set this session, never silently omitted.

Run (takes ~15-25 minutes, dominated by the Local Judge):
    .venv/Scripts/python -m controlplane.experiments.evaluate_judge_calibration
"""

from __future__ import annotations

import json
import random
import time
from collections import Counter
from datetime import date
from pathlib import Path

from controlplane.config import get_settings
from controlplane.evaluation.evaluators import EvaluationContext, GroundingEvaluator
from controlplane.evaluation.judge_evaluators import JudgeBackedEvaluator
from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.judge.local_judge import LocalJudge
from controlplane.judge.remote_judge import RemoteJudge

_DATASET_PATH = Path("data/raw/generated/rag_cases.json")
DATASET_ID = "rag_cases_derived_grounding_calibration"
DATASET_VERSION = "v0.1"
_N_PER_CLASS = 10
_LABELS = ["SUPPORTED", "UNSUPPORTED"]


def _build_cases() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        records = json.load(f)
    sufficient = [r for r in records if r["evidence_sufficiency"] == "SUFFICIENT" and r.get("expected_answer")]
    random.Random(42).shuffle(sufficient)
    if len(sufficient) < _N_PER_CLASS * 2:
        raise RuntimeError(f"need at least {_N_PER_CLASS * 2} SUFFICIENT records, found {len(sufficient)}")

    positives = sufficient[:_N_PER_CLASS]
    distractors = sufficient[_N_PER_CLASS : _N_PER_CLASS * 2]

    cases = []
    for i, r in enumerate(positives):
        cases.append({
            "case_id": f"JCAL-POS-{i}", "query": r["query"], "evidence": r["documents"],
            "answer": r["expected_answer"], "ground_truth_label": "SUPPORTED",
        })
    for i, (r, other) in enumerate(zip(positives, distractors)):
        cases.append({
            "case_id": f"JCAL-NEG-{i}", "query": r["query"], "evidence": r["documents"],
            "answer": other["expected_answer"], "ground_truth_label": "UNSUPPORTED",
        })
    return cases


def _binary(label: str | None) -> str:
    return "SUPPORTED" if label == "SUPPORTED" else "UNSUPPORTED"


def _run_scorer(name: str, scorer, cases: list[dict]) -> dict:
    y_true, y_pred, raw_labels, latencies_ms, statuses = [], [], [], [], []
    for case in cases:
        ctx = EvaluationContext(query=case["query"], answer=case["answer"], evidence_texts=case["evidence"])
        start = time.monotonic()
        result = scorer.evaluate(ctx)
        latencies_ms.append(int((time.monotonic() - start) * 1000))
        y_true.append(case["ground_truth_label"])
        y_pred.append(_binary(result.label))
        raw_labels.append(result.label)
        statuses.append(result.status.value)

    per_class = per_class_precision_recall_f1(y_true, y_pred, _LABELS)
    return {
        "scorer": name,
        "sample_count": len(cases),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(per_class),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, _LABELS),
        "raw_label_distribution": dict(Counter(raw_labels)),
        "status_distribution": dict(Counter(statuses)),
        "latency_ms_mean": sum(latencies_ms) / len(latencies_ms) if latencies_ms else None,
        "latency_ms_max": max(latencies_ms) if latencies_ms else None,
    }


def main() -> None:
    cases = _build_cases()
    settings = get_settings()

    experiment_id = record_experiment(
        experiment_name="judge_calibration_grounding",
        component="evaluation_judge",
        algorithm="deterministic_vs_local_judge_vs_remote_judge",
        algorithm_version="v1",
    )

    results = {}

    print(f"Running deterministic baseline ({len(cases)} cases)...")
    det_metrics = _run_scorer("deterministic_lexical", GroundingEvaluator(), cases)
    results["deterministic_lexical"] = det_metrics
    run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                         model="coverage_overlap_lexical", configuration={}, notes="SMOKE_TEST scale, derived ground truth")
    record_evaluation(experiment_run_id=run_id, split=None, metrics=det_metrics)
    print(f"  accuracy={det_metrics['accuracy']:.3f} macro_f1={det_metrics['macro_f1']:.3f} latency_ms_mean={det_metrics['latency_ms_mean']:.2f}")

    print(f"Running Local Judge ({len(cases)} cases, ~30-90s/case -- this will take a while)...")
    local_judge_evaluator = JudgeBackedEvaluator(LocalJudge(max_new_tokens=80), "grounding")
    local_metrics = _run_scorer("local_judge", local_judge_evaluator, cases)
    results["local_judge"] = local_metrics
    run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                         model=LocalJudge.name if hasattr(LocalJudge, "name") else "local_qwen2.5-1.5b-instruct",
                         configuration={"max_new_tokens": 80}, notes="SMOKE_TEST scale, derived ground truth, CPU-only")
    record_evaluation(experiment_run_id=run_id, split=None, metrics=local_metrics)
    print(f"  accuracy={local_metrics['accuracy']:.3f} macro_f1={local_metrics['macro_f1']:.3f} latency_ms_mean={local_metrics['latency_ms_mean']:.0f}")

    gemini_keys = [k for k in (settings.gemini_api_key_1, settings.gemini_api_key_2) if k]
    if gemini_keys and settings.gemini_model:
        print(f"Running Remote Judge / Gemini ({len(cases)} cases)...")
        remote_judge_evaluator = JudgeBackedEvaluator(RemoteJudge(settings), "grounding")
        remote_metrics = _run_scorer("remote_judge_gemini", remote_judge_evaluator, cases)
        results["remote_judge_gemini"] = remote_metrics
        run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                             model=settings.gemini_model, configuration={}, notes="SMOKE_TEST scale, derived ground truth")
        record_evaluation(experiment_run_id=run_id, split=None, metrics=remote_metrics)
        print(f"  accuracy={remote_metrics['accuracy']:.3f} macro_f1={remote_metrics['macro_f1']:.3f} latency_ms_mean={remote_metrics['latency_ms_mean']:.0f}")
    else:
        print("Skipping Remote Judge / Gemini: NOT_MEASURED (no GEMINI_API_KEY_1/2 or GEMINI_MODEL set this session)")
        results["remote_judge_gemini"] = "NOT_MEASURED -- no GEMINI_API_KEY_1/2 or GEMINI_MODEL set this session"

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"judge_calibration_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "results": results}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
