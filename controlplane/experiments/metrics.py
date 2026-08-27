"""Classification metrics -- deliberately dependency-free (no scikit-learn)
since the computations needed (accuracy, per-class P/R/F1, confusion
matrix, multi-label micro/macro F1) are straightforward and this keeps
the dependency footprint minimal (bootstrap Rule 4/5).
"""

from __future__ import annotations

from collections import Counter


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    return sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)


def confusion_matrix(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    matrix = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        if t in matrix and p in matrix[t]:
            matrix[t][p] += 1
    return matrix


def per_class_precision_recall_f1(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    result = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        support = sum(1 for t in y_true if t == label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        result[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
    return result


def macro_f1(per_class: dict) -> float:
    scored = [v["f1"] for v in per_class.values() if v["support"] > 0]
    return sum(scored) / len(scored) if scored else 0.0


def multilabel_micro_macro_f1(y_true: list[set[str]], y_pred: list[set[str]], labels: list[str]) -> dict:
    per_label = {}
    tp_total = fp_total = fn_total = 0
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if label in t and label in p)
        fp = sum(1 for t, p in zip(y_true, y_pred) if label not in t and label in p)
        fn = sum(1 for t, p in zip(y_true, y_pred) if label in t and label not in p)
        support = sum(1 for t in y_true if label in t)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
        tp_total += tp
        fp_total += fp
        fn_total += fn

    micro_precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else 0.0
    micro_recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if (micro_precision + micro_recall)
        else 0.0
    )
    scored = [v["f1"] for v in per_label.values() if v["support"] > 0]
    macro = sum(scored) / len(scored) if scored else 0.0

    return {"per_label": per_label, "micro_f1": micro_f1, "macro_f1": macro}


def false_negative_rate(y_true_positive: list[bool], y_pred_positive: list[bool]) -> float | str:
    """For "did we MISS a true positive" analysis (bootstrap SS19:
    "prioritize false-negative analysis" for high-risk categories)."""
    positives = sum(1 for t in y_true_positive if t)
    if positives == 0:
        return "NOT_MEASURED"
    missed = sum(1 for t, p in zip(y_true_positive, y_pred_positive) if t and not p)
    return missed / positives
