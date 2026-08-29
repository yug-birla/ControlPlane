"""Evidence view data (§59): Baseline vs ControlPlane, and which
components produced the difference.

READS ONLY COMMITTED RESULT FILES. Every number rendered by this view
came out of an experiment run that wrote a JSON file under
``docs/EVALUATION/RESULTS/``. Nothing here computes, estimates, or
interpolates a metric -- if a file is absent the view says so rather
than showing a plausible-looking blank. That rule exists because a
comparison dashboard is exactly where a fabricated number would be
least likely to be questioned.

COMPONENT ATTRIBUTION is derived, but only from data the benchmark
actually recorded per case: ``flagged_evaluators`` on each row. The
over-control attribution below is a count of which evaluator fired on
benign cases that ControlPlane withheld -- not an opinion about which
component is responsible.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

_RESULTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "EVALUATION" / "RESULTS"

# Rendered in this order, with the direction that counts as better, so
# the template never has to guess whether up or down is good.
_HEADLINE_METRICS = [
    ("key_fact_accuracy_factual_cases", "Key-fact accuracy", "higher"),
    ("hallucination_rate_factual_cases", "Hallucination rate", "lower"),
    ("grounding_supported_rate_factual_cases", "Grounding supported", "higher"),
    ("appropriate_abstention_rate_unanswerable", "Abstention when unanswerable", "higher"),
    ("confabulation_rate_unanswerable", "Confabulation when unanswerable", "lower"),
    ("control_rate_on_unsafe_cases", "Control on unsafe cases", "higher"),
    ("control_rate_on_benign_cases", "Over-control on benign cases", "lower"),
    ("latency_ms_mean", "Mean latency (ms)", "lower"),
    ("output_tokens_total", "Output tokens (total)", "lower"),
]


def _latest(prefix: str) -> Path | None:
    """Most recent result file for an experiment family. Filenames carry
    an ISO date, so lexical sort is chronological."""
    matches = sorted(_RESULTS_DIR.glob(f"{prefix}_*.json"))
    return matches[-1] if matches else None


def _load(prefix: str) -> tuple[dict | None, str | None]:
    path = _latest(prefix)
    if path is None:
        return None, None
    with open(path, encoding="utf-8") as f:
        return json.load(f), path.name


def _per_category(baseline_rows: list[dict], controlplane_rows: list[dict]) -> list[dict]:
    by_id = {r["case_id"]: r for r in baseline_rows}
    grouped: dict[str, dict] = {}
    for row in controlplane_rows:
        category = row.get("category") or "UNCATEGORISED"
        bucket = grouped.setdefault(category, {"category": category, "n": 0,
                                               "baseline_correct": 0, "controlplane_correct": 0,
                                               "baseline_hallucinations": 0, "controlplane_hallucinations": 0})
        base = by_id.get(row["case_id"], {})
        bucket["n"] += 1
        bucket["baseline_correct"] += bool(base.get("key_fact_correct"))
        bucket["controlplane_correct"] += bool(row.get("key_fact_correct"))
        bucket["baseline_hallucinations"] += bool(base.get("hallucinated_fact"))
        bucket["controlplane_hallucinations"] += bool(row.get("hallucinated_fact"))
    return sorted(grouped.values(), key=lambda b: (-b["n"], b["category"]))


def _over_control_attribution(controlplane_rows: list[dict]) -> list[dict]:
    """Which evaluator fired on benign cases that were withheld.

    This is the honest form of "which component hurt results": a direct
    count from recorded per-case data. A case can flag several
    evaluators, so the counts are not mutually exclusive and the total
    may exceed the number of cases -- stated here rather than silently
    normalised away."""
    counts: Counter = Counter()
    affected = 0
    for row in controlplane_rows:
        if not row.get("controlled"):
            continue
        if row.get("category") in {"HIGH_RISK_ACTION", "PROMPT_INJECTION", "UNANSWERABLE"}:
            continue  # controlling these is correct behaviour, not a cost
        affected += 1
        for evaluator in row.get("flagged_evaluators") or []:
            counts[evaluator] += 1
    return [{"evaluator": name, "cases": n, "of_controlled_benign": affected}
            for name, n in counts.most_common()]


def _decision_mix(rows: list[dict]) -> list[dict]:
    counts = Counter(r.get("decision") or "UNKNOWN" for r in rows)
    total = sum(counts.values()) or 1
    return [{"label": k, "count": v, "share": v / total} for k, v in counts.most_common()]


def build_evidence() -> dict:
    """Everything the evidence page renders. Missing files degrade to an
    explicit ``available: False`` rather than an empty table that reads
    like a measured zero."""
    bvc, bvc_file = _load("baseline_vs_controlplane")
    ablations, ablations_file = _load("ablations")
    injection, injection_file = _load("injection_domain_shift")

    evidence: dict = {
        "baseline_vs_controlplane": {"available": False},
        "ablations": {"available": False},
        "injection_domain_shift": {"available": False},
    }

    if bvc:
        base_metrics = bvc["baseline"]["metrics"]
        cp_metrics = bvc["controlplane"]["metrics"]
        comparison = []
        for key, label, direction in _HEADLINE_METRICS:
            base_value, cp_value = base_metrics.get(key), cp_metrics.get(key)
            if base_value is None or cp_value is None:
                continue
            delta = cp_value - base_value
            improved = delta > 0 if direction == "higher" else delta < 0
            comparison.append({
                "label": label, "key": key, "baseline": base_value, "controlplane": cp_value,
                "delta": delta, "improved": improved, "unchanged": delta == 0, "direction": direction,
            })
        evidence["baseline_vs_controlplane"] = {
            "available": True,
            "source_file": bvc_file,
            "experiment_id": bvc.get("experiment_id"),
            "dataset_id": bvc.get("dataset_id"),
            "dataset_version": bvc.get("dataset_version"),
            "model": bvc.get("model"),
            "sample_count": base_metrics.get("sample_count"),
            "scale": "DEVELOPMENT_TEST",
            "comparison": comparison,
            "per_category": _per_category(bvc["baseline"]["rows"], bvc["controlplane"]["rows"]),
            "over_control_attribution": _over_control_attribution(bvc["controlplane"]["rows"]),
            "decision_mix": _decision_mix(bvc["controlplane"]["rows"]),
            "provider_failures": sum(1 for r in bvc["controlplane"]["rows"] if r.get("provider_failed")),
        }

    if ablations:
        evidence["ablations"] = {
            "available": True, "source_file": ablations_file,
            "experiment_id": ablations.get("experiment_id"),
            "conditions": [
                {"condition": name,
                 "sample_count": m.get("sample_count"),
                 "key_fact_accuracy": m.get("key_fact_accuracy_factual_cases"),
                 "hallucination_rate": m.get("hallucination_rate_factual_cases"),
                 "grounding_supported": m.get("grounding_supported_rate_factual_cases"),
                 "control_on_unsafe": m.get("control_rate_on_unsafe_cases"),
                 "over_control_benign": m.get("control_rate_on_benign_cases"),
                 "latency_ms_mean": m.get("latency_ms_mean")}
                for name, m in (ablations.get("results") or {}).items()
            ],
            "note": ablations.get("rescoring_note"),
        }

    if injection:
        evidence["injection_domain_shift"] = {
            "available": True, "source_file": injection_file,
            "experiment_id": injection.get("experiment_id"),
            "conditions": [
                {"condition": name,
                 "deepset_macro_f1": sets.get("deepset_test", {}).get("macro_f1"),
                 "enterprise_macro_f1": sets.get("enterprise_test", {}).get("macro_f1"),
                 "validation_macro_f1": sets.get("enterprise_validation", {}).get("macro_f1"),
                 "live_queries_correct": sets.get("held_out_live_queries_correct")}
                for name, sets in (injection.get("results") or {}).items()
            ],
        }

    return evidence
