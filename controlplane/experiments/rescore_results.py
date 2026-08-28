"""Re-score a saved baseline-vs-ControlPlane / ablation result file with
the CURRENT scoring code, without re-running any model inference.

Exists because Milestone 9's error analysis found a real bug in the
scoring harness itself (bare-number substring matching: the
contradicting value "6" matched inside the correct answer "16 weeks",
scoring a correct answer as a hallucination). Fixing the scorer would
otherwise have meant ~45 minutes of CPU-only regeneration to get
comparable numbers -- but the raw per-case answers are saved in the
result JSON, so re-scoring is a seconds-long, deterministic operation.

Keeping this as an explicit, committed script rather than editing
numbers by hand is the reproducibility requirement (bootstrap SS31):
anyone can re-derive the corrected metrics from the saved answers.

Run:
    .venv/Scripts/python -m controlplane.experiments.rescore_results <path.json> [<path.json> ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from controlplane.experiments.evaluate_baseline_vs_controlplane import (
    _aggregate,
    _gold_evidence,
    _load_cases,
    _score_answer,
)

_SCORE_KEYS = (
    "asserted_an_answer", "key_fact_correct", "hallucinated_fact",
    "grounding_label", "grounding_supported",
    "appropriately_abstained", "confabulated_when_unanswerable",
)


def rescore_rows(rows: list[dict], cases_by_id: dict[str, dict]) -> list[dict]:
    rescored = []
    for row in rows:
        case = cases_by_id[row["case_id"]]
        fresh = _score_answer(case, row.get("answer"), _gold_evidence(case.get("gold_document")))
        merged = {k: v for k, v in row.items() if k not in _SCORE_KEYS}
        merged.update(fresh)
        rescored.append(merged)
    return rescored


def rescore_file(path: Path) -> dict:
    cases = _load_cases()
    cases_by_id = {c["case_id"]: c for c in cases}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    changed = 0

    # baseline_vs_controlplane layout: {"baseline": {...}, "controlplane": {...}}
    for condition in ("baseline", "controlplane"):
        if condition in data and isinstance(data[condition], dict) and "rows" in data[condition]:
            old = data[condition]["rows"]
            new = rescore_rows(old, cases_by_id)
            changed += sum(
                1 for a, b in zip(old, new)
                if a.get("key_fact_correct") != b.get("key_fact_correct")
                or a.get("hallucinated_fact") != b.get("hallucinated_fact")
            )
            data[condition]["rows"] = new
            data[condition]["metrics"] = _aggregate(new, cases)

    # ablations layout: {"rows": {condition: [...]}, "results": {condition: metrics}}
    if isinstance(data.get("rows"), dict):
        for name, old in data["rows"].items():
            new = rescore_rows(old, cases_by_id)
            changed += sum(
                1 for a, b in zip(old, new)
                if a.get("key_fact_correct") != b.get("key_fact_correct")
                or a.get("hallucinated_fact") != b.get("hallucinated_fact")
            )
            data["rows"][name] = new
            metrics = _aggregate(new, cases)
            prior = data.get("results", {}).get(name, {})
            if "retrieval_rate_on_corpus_answerable" in prior:
                metrics["retrieval_rate_on_corpus_answerable"] = prior["retrieval_rate_on_corpus_answerable"]
            data.setdefault("results", {})[name] = metrics

    data["rescored"] = True
    data["rescoring_note"] = (
        "Re-scored with the corrected token-boundary numeric matcher "
        "(controlplane.experiments.evaluate_baseline_vs_controlplane._mentions). "
        "Model answers are unchanged -- only the deterministic scoring of them."
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return {"path": str(path), "cases_whose_score_changed": changed}


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        paths = sorted(Path("docs/EVALUATION/RESULTS").glob("baseline_vs_controlplane_*.json"))
        paths += sorted(Path("docs/EVALUATION/RESULTS").glob("ablations_*.json"))
    for path in paths:
        print(rescore_file(path))


if __name__ == "__main__":
    main()
