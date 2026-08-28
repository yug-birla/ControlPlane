"""Judge HARD benchmark -- deterministic lexical grounding vs. Local
Judge vs. Remote Judge, on a genuinely difficult, hand-authored
3-way-labeled (SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED) benchmark.

Built in direct response to the honest finding in
docs/EVALUATION/EVALUATOR_RESULTS.md (Milestone 6): the previous
20-case calibration set was too easy (negatives were completely
off-topic distractors), so the deterministic lexical baseline reached
1.0 accuracy and the judge had no chance to show where it earns its
much higher cost. This benchmark specifically targets the failure modes
lexical overlap cannot handle: heavily paraphrased-but-correct answers
(different words, same meaning), hallucinated additions to an otherwise
correct answer, subtly wrong numbers close to the real value, and
conflicting evidence.

Dataset: data/raw/generated/judge_hard_cases.json (24 cases, provenance
HUMAN, hand-authored from the real 30-document corpus's actual facts --
not fabricated).

Run (takes ~25-35 minutes, dominated by the Local Judge):
    .venv/Scripts/python -m controlplane.experiments.evaluate_judge_hard_benchmark
"""

from __future__ import annotations

import json
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

_DATASET_PATH = Path("data/raw/generated/judge_hard_cases.json")
DATASET_ID = "judge_hard_cases"
DATASET_VERSION = "v0.1"
_LABELS = ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"]


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _normalize(label: str | None) -> str:
    return label if label in _LABELS else "UNSUPPORTED"


def _run_scorer(name: str, scorer, cases: list[dict]) -> dict:
    y_true, y_pred, raw_labels, latencies_ms, by_category_correct = [], [], [], [], Counter()
    by_category_total = Counter()
    errors = []
    for case in cases:
        ctx = EvaluationContext(query=case["query"], answer=case["answer"], evidence_texts=case["evidence"])
        start = time.monotonic()
        result = scorer.evaluate(ctx)
        latencies_ms.append(int((time.monotonic() - start) * 1000))
        pred = _normalize(result.label)
        y_true.append(case["label"])
        y_pred.append(pred)
        raw_labels.append(result.label)
        by_category_total[case["category"]] += 1
        if pred == case["label"]:
            by_category_correct[case["category"]] += 1
        else:
            errors.append({"case_id": case["case_id"], "category": case["category"], "expected": case["label"], "actual": pred})

    per_class = per_class_precision_recall_f1(y_true, y_pred, _LABELS)
    by_category = {
        cat: f"{by_category_correct[cat]}/{by_category_total[cat]}" for cat in sorted(by_category_total)
    }
    return {
        "scorer": name,
        "sample_count": len(cases),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(per_class),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, _LABELS),
        "accuracy_by_category": by_category,
        "raw_label_distribution": dict(Counter(raw_labels)),
        "latency_ms_mean": sum(latencies_ms) / len(latencies_ms) if latencies_ms else None,
        "errors": errors,
    }


def main() -> None:
    cases = _load()
    settings = get_settings()

    experiment_id = record_experiment(
        experiment_name="judge_hard_benchmark",
        component="evaluation_judge",
        algorithm="deterministic_vs_local_judge_vs_remote_judge_hard",
        algorithm_version="v1",
    )

    results = {}

    print(f"Running deterministic baseline ({len(cases)} cases)...")
    det_metrics = _run_scorer("deterministic_lexical", GroundingEvaluator(), cases)
    results["deterministic_lexical"] = det_metrics
    run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                         model="coverage_overlap_lexical", configuration={}, notes="Hard benchmark: paraphrase/hallucination/subtle-error/conflict cases")
    record_evaluation(experiment_run_id=run_id, split=None, metrics=det_metrics)
    print(f"  accuracy={det_metrics['accuracy']:.3f} macro_f1={det_metrics['macro_f1']:.3f}")
    print(f"  by_category={det_metrics['accuracy_by_category']}")

    print(f"Running Local Judge ({len(cases)} cases, ~60-90s/case -- this will take a while)...")
    local_judge_evaluator = JudgeBackedEvaluator(LocalJudge(max_new_tokens=100), "grounding")
    local_metrics = _run_scorer("local_judge", local_judge_evaluator, cases)
    results["local_judge"] = local_metrics
    run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                         model="local_qwen2.5-1.5b-instruct", configuration={"max_new_tokens": 100},
                         notes="Hard benchmark, CPU-only")
    record_evaluation(experiment_run_id=run_id, split=None, metrics=local_metrics)
    print(f"  accuracy={local_metrics['accuracy']:.3f} macro_f1={local_metrics['macro_f1']:.3f} latency_ms_mean={local_metrics['latency_ms_mean']:.0f}")
    print(f"  by_category={local_metrics['accuracy_by_category']}")

    gemini_keys = [k for k in (settings.gemini_api_key_1, settings.gemini_api_key_2) if k]
    if gemini_keys and settings.gemini_model:
        print(f"Running Remote Judge / Gemini ({len(cases)} cases)...")
        remote_judge_evaluator = JudgeBackedEvaluator(RemoteJudge(settings), "grounding")
        remote_metrics = _run_scorer("remote_judge_gemini", remote_judge_evaluator, cases)
        results["remote_judge_gemini"] = remote_metrics
        run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                             model=settings.gemini_model, configuration={}, notes="Hard benchmark")
        record_evaluation(experiment_run_id=run_id, split=None, metrics=remote_metrics)
        print(f"  accuracy={remote_metrics['accuracy']:.3f} macro_f1={remote_metrics['macro_f1']:.3f}")
    else:
        print("Skipping Remote Judge / Gemini: NOT_MEASURED (no GEMINI_API_KEY_1/2 or GEMINI_MODEL set this session)")
        results["remote_judge_gemini"] = "NOT_MEASURED -- no GEMINI_API_KEY_1/2 or GEMINI_MODEL set this session"

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"judge_hard_benchmark_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "results": results}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
