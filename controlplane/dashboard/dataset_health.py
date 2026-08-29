"""Dataset health view data (§58).

WHAT THIS IS FOR. The project has accumulated roughly two dozen
evaluation datasets across sixteen milestones. The failure mode this
view exists to prevent is not "a dataset is missing" -- it is a dataset
that is present, gets benchmarked, and quietly cannot support the claim
being made from it: one split, no negative class, thirty cases used as
though they were a benchmark, or a "test" set that overlaps its own
reference data.

EVERY FIELD IS READ FROM THE FILE ON DISK. Sizes, label distributions
and splits are counted at page load from the actual JSON; nothing is
transcribed from a registry that could drift from the data. Where a
property cannot be determined from the file, it is reported as unknown
rather than assumed.

THE WARNINGS ARE THE POINT. A row with a green count and no warnings is
less informative than a row that says "single split -- any threshold
tuned on this data is tuned on its own test set". The checks below are
deliberately the ones this project has actually been burned by:

  no held-out split      k=31 won on a 16-case validation split and lost
                         on the 116-case test set; entailment was best
                         on dev and worst on test. Both were caught only
                         because the splits were separate.
  single-class           a reference set given only benign in-domain
                         examples would teach "enterprise phrasing =>
                         safe" and pass its own false-positive test.
  split overlap          k-NN's "model" IS its reference data, so an
                         evaluation example appearing there makes the
                         reported number meaningless.
  small sample           the 62-case run has per-category rates resting
                         on one to three cases.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_GENERATED = _ROOT / "data" / "raw" / "generated"
_EXTERNAL = _ROOT / "data" / "external"
_RESULTS = _ROOT / "docs" / "EVALUATION" / "RESULTS"

# Sample counts below this cannot support a rate. Chosen to match the
# scale labels already used in this project's docs: anything under 30 is
# SMOKE_TEST or DEVELOPMENT_TEST, never SERIOUS_BENCHMARK.
_SMALL_SAMPLE = 30

# Which result-file family reports on which dataset, so a dataset can be
# shown with the date it was last actually measured rather than merely
# the date its file changed.
_BENCHMARK_PREFIXES = {
    "baseline_vs_controlplane_cases": "baseline_vs_controlplane",
    "enterprise_injection_cases": "injection_domain_shift",
    "reasoning_cases": "reasoning_consistency",
    "factuality_cases": "factuality_provenance",
    "multi_agent_cases": "multi_agent",
    "rag_retrieval_relevance_cases": "reranker_comparison",
    "bias_paired_cases": "bias_paired_comparison",
    "chat_history_sessions": "chat_history",
    "prompt_injection_cases": "prompt_injection",
}

_LABEL_KEYS = ("expected_label", "label", "expected_composition_risk", "risk", "category")


def _read(path: Path) -> list[dict] | None:
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, list) else None


def _label_field(records: list[dict]) -> str | None:
    for key in _LABEL_KEYS:
        if any(key in r for r in records):
            return key
    return None


def _last_benchmarked(dataset_stem: str) -> str | None:
    prefix = _BENCHMARK_PREFIXES.get(dataset_stem)
    if not prefix:
        return None
    matches = sorted(_RESULTS.glob(f"{prefix}_*.json"))
    return matches[-1].name if matches else None


def _warnings(records: list[dict], splits: dict[str, int], labels: dict[str, int],
              overlap: int) -> list[str]:
    warnings: list[str] = []
    if len(records) < _SMALL_SAMPLE:
        warnings.append(
            f"{len(records)} cases -- DEVELOPMENT_TEST scale; per-category rates here rest on very few cases")
    if len(splits) <= 1:
        warnings.append(
            "no held-out split -- any threshold tuned on this data is tuned on its own test set")
    if labels and len(labels) == 1:
        warnings.append(
            f"single class ({next(iter(labels))}) -- cannot measure false positives")
    if labels and len(labels) > 1:
        counts = sorted(labels.values())
        if counts[-1] >= 4 * max(counts[0], 1):
            warnings.append(
                f"imbalanced {counts[-1]}:{counts[0]} -- accuracy will be dominated by the majority class")
    if overlap:
        warnings.append(f"LEAKAGE: {overlap} case(s) appear in more than one split")
    return warnings


def _split_overlap(records: list[dict]) -> int:
    by_split: dict[str, set] = {}
    for record in records:
        split = record.get("split")
        if split is None:
            return 0
        key = record.get("query") or record.get("answer") or record.get("case_id")
        by_split.setdefault(split, set()).add(key)
    seen: Counter = Counter()
    for keys in by_split.values():
        seen.update(keys)
    return sum(1 for _, n in seen.items() if n > 1)


def _describe(path: Path, provenance_default: str) -> dict | None:
    records = _read(path)
    if records is None:
        return None
    label_field = _label_field(records)
    labels = dict(Counter(str(r.get(label_field)) for r in records if r.get(label_field) is not None)) if label_field else {}
    splits = dict(Counter(str(r.get("split")) for r in records if r.get("split")))
    provenance = dict(Counter(str(r.get("provenance", provenance_default)) for r in records))
    overlap = _split_overlap(records)

    return {
        "dataset": path.stem,
        "path": str(path.relative_to(_ROOT)).replace("\\", "/"),
        "cases": len(records),
        "splits": splits or {"(single)": len(records)},
        "label_field": label_field,
        "labels": labels,
        "provenance": provenance,
        "last_benchmarked": _last_benchmarked(path.stem),
        "warnings": _warnings(records, splits, labels, overlap),
    }


def build_dataset_health() -> dict:
    rows: list[dict] = []
    for path in sorted(_GENERATED.glob("*.json")):
        described = _describe(path, "SYNTHETIC")
        if described:
            rows.append(described)
    for path in sorted(_EXTERNAL.glob("*/*.json")):
        described = _describe(path, "EXTERNAL")
        if described:
            rows.append(described)

    total_cases = sum(r["cases"] for r in rows)
    with_splits = sum(1 for r in rows if len(r["splits"]) > 1)
    return {
        "datasets": sorted(rows, key=lambda r: -r["cases"]),
        "dataset_count": len(rows),
        "total_cases": total_cases,
        "with_held_out_split": with_splits,
        "flagged": sum(1 for r in rows if r["warnings"]),
        "never_benchmarked": sorted(r["dataset"] for r in rows if not r["last_benchmarked"]),
    }
