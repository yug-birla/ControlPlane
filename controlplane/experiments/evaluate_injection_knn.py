"""Deterministic keyword baseline vs. Embedding k-NN, on the held-out
TEST split (116 examples) of the real `deepset/prompt-injections`
dataset -- the direct "OLD BASELINE -> IMPROVE -> TEST -> COMPARE ->
ADOPT/REJECT" experiment (bootstrap SS7/SS59) following the 98.5% false
negative rate found in `evaluate_safety_external.py`.

The k-NN detector's reference set is the TRAIN split (546 examples) --
disjoint from the TEST split being scored here, so this is a genuine
held-out evaluation, not a report of accuracy against examples also
used as reference/training data.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_injection_knn
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.evaluation.evaluators import EvaluationContext, PromptInjectionEvaluator
from controlplane.evaluation.injection_knn import EmbeddingKNNInjectionDetector
from controlplane.experiments.metrics import accuracy, confusion_matrix, macro_f1, per_class_precision_recall_f1
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_DATASET_PATH = Path("data/external/deepset_prompt_injections/prompt_injections_normalized.json")
DATASET_ID = "deepset_prompt_injections"
DATASET_VERSION = "4f61ecb038e9c3fb77e21034b22511b523772cdd"
_LABELS = ["INJECTION_PATTERN_DETECTED", "NO_PATTERN_DETECTED"]


def _load() -> tuple[list[dict], list[dict]]:
    with open(_DATASET_PATH, encoding="utf-8") as f:
        records = json.load(f)
    train = [r for r in records if r["split"] == "train"]
    test = [r for r in records if r["split"] == "test"]
    return train, test


def _score(name: str, y_true: list[str], y_pred: list[str]) -> dict:
    per_class = per_class_precision_recall_f1(y_true, y_pred, _LABELS)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == "INJECTION_PATTERN_DETECTED" and p != "INJECTION_PATTERN_DETECTED")
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == "NO_PATTERN_DETECTED" and p == "INJECTION_PATTERN_DETECTED")
    n_pos = sum(1 for t in y_true if t == "INJECTION_PATTERN_DETECTED")
    n_neg = sum(1 for t in y_true if t == "NO_PATTERN_DETECTED")
    return {
        "scorer": name,
        "sample_count": len(y_true),
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(per_class),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, _LABELS),
        "false_negative_rate": fn / n_pos if n_pos else None,
        "false_positive_rate": fp / n_neg if n_neg else None,
    }


def _calibrate_threshold(train: list[dict]) -> float:
    """Grid-search the similarity-reject threshold on a held-out SLICE
    of TRAIN only (80/20 split within TRAIN) -- never touches TEST.
    Found necessary after a real end-to-end regression: a threshold-less
    k-NN flagged a benign SQL query as an injection because majority
    vote always returns a label even among near-orthogonal (cosine
    ~0.2) neighbors."""
    split_point = int(len(train) * 0.8)
    ref, calib = train[:split_point], train[split_point:]
    calib_true = [c["expected_label"] for c in calib]

    best_threshold, best_f1 = 0.0, -1.0
    for threshold in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
        detector = EmbeddingKNNInjectionDetector(ref, k=5, similarity_threshold=threshold)
        calib_pred = [detector.classify(c["query"]).label for c in calib]
        per_class = per_class_precision_recall_f1(calib_true, calib_pred, _LABELS)
        f1 = macro_f1(per_class)
        print(f"  threshold={threshold:.2f} -> calibration macro_f1={f1:.3f}")
        if f1 > best_f1:
            best_threshold, best_f1 = threshold, f1
    print(f"Selected similarity_threshold={best_threshold} (calibration macro_f1={best_f1:.3f})")
    return best_threshold


def main() -> None:
    train, test = _load()

    experiment_id = record_experiment(
        experiment_name="prompt_injection_keyword_vs_knn",
        component="evaluation_safety",
        algorithm="deterministic_keyword_vs_embedding_knn",
        algorithm_version="v2",
    )

    print(f"Held-out TEST split: {len(test)} examples. k-NN reference (TRAIN split): {len(train)} examples.")

    keyword_evaluator = PromptInjectionEvaluator(use_semantic_fallback=False)
    y_true = [c["expected_label"] for c in test]
    y_pred_keyword = [keyword_evaluator.evaluate(EvaluationContext(query=c["query"], answer="placeholder")).label for c in test]
    keyword_metrics = _score("deterministic_keyword_list", y_true, y_pred_keyword)
    run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                         model="prompt_injection_pattern_v0", configuration={},
                         notes="Held-out TEST split of the real dataset (116 examples)")
    record_evaluation(experiment_run_id=run_id, split="test", metrics=keyword_metrics)
    print(f"Deterministic keyword list: accuracy={keyword_metrics['accuracy']:.3f} macro_f1={keyword_metrics['macro_f1']:.3f} "
          f"fn_rate={keyword_metrics['false_negative_rate']:.3f} fp_rate={keyword_metrics['false_positive_rate']:.3f}")

    print("Calibrating similarity_threshold on a held-out 20% slice of TRAIN (never TEST)...")
    threshold = _calibrate_threshold(train)

    print(f"Building final embedding k-NN detector (reference: all {len(train)} TRAIN examples)...")
    knn = EmbeddingKNNInjectionDetector(train, k=5, similarity_threshold=threshold)
    y_pred_knn = [knn.classify(c["query"]).label for c in test]
    knn_metrics = _score("embedding_knn_k5", y_true, y_pred_knn)
    run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                         model="injection_knn_v0", configuration={"k": 5, "similarity_threshold": threshold, "reference_size": len(train)},
                         notes="Held-out TEST split; reference set is the disjoint TRAIN split; threshold calibrated on a TRAIN-internal slice, never TEST")
    record_evaluation(experiment_run_id=run_id, split="test", metrics=knn_metrics)
    print(f"Embedding k-NN (k=5, threshold={threshold}): accuracy={knn_metrics['accuracy']:.3f} macro_f1={knn_metrics['macro_f1']:.3f} "
          f"fn_rate={knn_metrics['false_negative_rate']:.3f} fp_rate={knn_metrics['false_positive_rate']:.3f}")

    print("Building combined (keyword + k-NN) detector, matching the live default...")
    print(f"NOTE: this measures PromptInjectionEvaluator's actual live default -- if that default's "
          f"similarity_threshold differs from the {threshold} calibrated here, update "
          f"controlplane.evaluation.injection_knn.EmbeddingKNNInjectionDetector's default to match.")
    combined_evaluator = PromptInjectionEvaluator(use_semantic_fallback=True)
    y_pred_combined = [combined_evaluator.evaluate(EvaluationContext(query=c["query"], answer="placeholder")).label for c in test]
    combined_metrics = _score("keyword_plus_knn_combined", y_true, y_pred_combined)
    run_id = record_run(experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
                         model="prompt_injection_evaluator_v2_combined", configuration={"k": 5, "similarity_threshold": threshold},
                         notes="Matches the live PromptInjectionEvaluator default (keyword layer, then k-NN fallback)")
    record_evaluation(experiment_run_id=run_id, split="test", metrics=combined_metrics)
    print(f"Combined (live default): accuracy={combined_metrics['accuracy']:.3f} macro_f1={combined_metrics['macro_f1']:.3f} "
          f"fn_rate={combined_metrics['false_negative_rate']:.3f} fp_rate={combined_metrics['false_positive_rate']:.3f}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"injection_keyword_vs_knn_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "similarity_threshold": threshold, "keyword": keyword_metrics, "knn": knn_metrics,
                    "combined": combined_metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
