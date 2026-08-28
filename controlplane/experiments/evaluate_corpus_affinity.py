"""Calibrate + evaluate corpus-affinity RAG routing against the keyword
baseline.

THE PROBLEM BEING MEASURED (Milestone 9 P0 finding): ``CapabilityHint.RAG``
was produced only by seven literal keywords, giving measured RAG-hint
recall of 1/19 on corpus-answerable questions -- so ControlPlane almost
never retrieved, and returned the same answer as an unmanaged model.

LEAKAGE DISCIPLINE (the reason for this file's split choices):

  CALIBRATION POSITIVES  ``rag_retrieval_relevance_cases.json`` (26
                         queries, provenance HUMAN, hand-authored in
                         Milestone 6 by reading all 30 corpus documents).
                         Guaranteed corpus-answerable.

  CALIBRATION NEGATIVES  ``query_profiles_large.json`` records whose
                         ``required_data_sources == ["public_knowledge"]``
                         -- genuinely general questions this corpus has
                         nothing to say about. Real labelled data already
                         in the repo, not written for this experiment.

  HELD-OUT TEST          ``baseline_vs_controlplane_cases.json``. NEVER
                         used to pick the threshold -- it is the set the
                         end-to-end product claim is reported on, so
                         tuning on it would invalidate that claim.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_corpus_affinity
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.query_intelligence.corpus_affinity import CorpusAffinityDetector
from controlplane.query_intelligence.rules import RuleBasedQueryProfiler

_POSITIVES_PATH = Path("data/raw/generated/rag_retrieval_relevance_cases.json")
_NEGATIVES_PATH = Path("data/raw/generated/query_profiles_large.json")
_HELDOUT_PATH = Path("data/raw/generated/baseline_vs_controlplane_cases.json")


def _load(path: Path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _calibration_sets() -> tuple[list[str], list[str]]:
    positives = [c["query"] for c in _load(_POSITIVES_PATH)]
    negatives = [
        r["query"]
        for r in _load(_NEGATIVES_PATH)
        if (r.get("required_data_sources") or []) == ["public_knowledge"]
    ]
    return positives, negatives


def _keyword_predicts_rag(profiler: RuleBasedQueryProfiler, query: str) -> bool:
    return any(h.value == "RAG" for h in profiler.profile(query).capability_hints)


def _metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    total = tp + fp + fn + tn
    return {
        "true_positives": tp, "false_positives": fp,
        "false_negatives": fn, "true_negatives": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "accuracy": (tp + tn) / total if total else 0.0,
    }


def _score_threshold(sims_pos: list[float], sims_neg: list[float], threshold: float) -> dict:
    tp = sum(1 for s in sims_pos if s >= threshold)
    fn = len(sims_pos) - tp
    fp = sum(1 for s in sims_neg if s >= threshold)
    tn = len(sims_neg) - fp
    return _metrics(tp, fp, fn, tn)


def main() -> None:
    profiler = RuleBasedQueryProfiler()
    detector = CorpusAffinityDetector()

    positives, negatives = _calibration_sets()
    print(f"Calibration: {len(positives)} positives, {len(negatives)} negatives\n")

    # --- Baseline: the keyword rule, on the same calibration data ---
    kw_tp = sum(1 for q in positives if _keyword_predicts_rag(profiler, q))
    kw_fp = sum(1 for q in negatives if _keyword_predicts_rag(profiler, q))
    keyword_metrics = _metrics(kw_tp, kw_fp, len(positives) - kw_tp, len(negatives) - kw_fp)
    print("KEYWORD BASELINE (calibration split):")
    print(f"  precision={keyword_metrics['precision']:.3f} recall={keyword_metrics['recall']:.3f} "
          f"f1={keyword_metrics['f1']:.3f}\n")

    # --- Grid search the similarity threshold ---
    sims_pos = [detector.assess(q).max_similarity for q in positives]
    sims_neg = [detector.assess(q).max_similarity for q in negatives]

    grid = [round(0.20 + 0.01 * i, 2) for i in range(41)]  # 0.20 .. 0.60
    scored = [(t, _score_threshold(sims_pos, sims_neg, t)) for t in grid]
    best_threshold, best = max(scored, key=lambda tm: (tm[1]["f1"], tm[1]["recall"]))

    print("CORPUS AFFINITY (calibration split), threshold sweep:")
    for t, m in scored:
        if round(t * 100) % 5 == 0:
            print(f"  t={t:.2f}  precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f}")
    print(f"\n  BEST threshold={best_threshold:.2f} f1={best['f1']:.3f} "
          f"precision={best['precision']:.3f} recall={best['recall']:.3f}\n")

    # --- Held-out evaluation: the set the product claim is reported on ---
    heldout = _load(_HELDOUT_PATH)
    ho_pos = [c["query"] for c in heldout if c.get("gold_document")]
    ho_neg = [c["query"] for c in heldout if not c.get("gold_document")]

    shipped = CorpusAffinityDetector(similarity_threshold=best_threshold)
    ho_tp = sum(1 for q in ho_pos if shipped.assess(q).is_corpus_answerable)
    ho_fp = sum(1 for q in ho_neg if shipped.assess(q).is_corpus_answerable)
    affinity_heldout = _metrics(ho_tp, ho_fp, len(ho_pos) - ho_tp, len(ho_neg) - ho_fp)

    kw_ho_tp = sum(1 for q in ho_pos if _keyword_predicts_rag(profiler, q))
    kw_ho_fp = sum(1 for q in ho_neg if _keyword_predicts_rag(profiler, q))
    keyword_heldout = _metrics(kw_ho_tp, kw_ho_fp, len(ho_pos) - kw_ho_tp, len(ho_neg) - kw_ho_fp)

    print(f"HELD-OUT ({len(ho_pos)} corpus-answerable, {len(ho_neg)} not):")
    print(f"  keyword baseline : precision={keyword_heldout['precision']:.3f} "
          f"recall={keyword_heldout['recall']:.3f} f1={keyword_heldout['f1']:.3f}")
    print(f"  corpus affinity  : precision={affinity_heldout['precision']:.3f} "
          f"recall={affinity_heldout['recall']:.3f} f1={affinity_heldout['f1']:.3f}")

    experiment_id = record_experiment(
        experiment_name="corpus_affinity_rag_routing",
        component="query_intelligence",
        algorithm="keyword_vs_embedding_corpus_affinity",
        algorithm_version="v1",
    )
    for name, metrics, split in (
        ("keyword_baseline", keyword_metrics, "calibration"),
        ("corpus_affinity", best, "calibration"),
        ("keyword_baseline", keyword_heldout, "heldout"),
        ("corpus_affinity", affinity_heldout, "heldout"),
    ):
        run_id = record_run(
            experiment_id=experiment_id,
            dataset_id="corpus_affinity_rag_routing",
            dataset_version="v0.1",
            model=name,
            configuration={"threshold": best_threshold if name == "corpus_affinity" else None},
            notes="positives=rag_retrieval_relevance_cases, negatives=public_knowledge query profiles; "
                  "held-out=baseline_vs_controlplane_cases (never used for threshold selection)",
        )
        record_evaluation(experiment_run_id=run_id, split=split, metrics=metrics)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"corpus_affinity_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment_id": experiment_id,
            "chosen_threshold": best_threshold,
            "calibration": {"keyword": keyword_metrics, "corpus_affinity": best,
                             "sweep": [{"threshold": t, **m} for t, m in scored]},
            "heldout": {"keyword": keyword_heldout, "corpus_affinity": affinity_heldout},
        }, f, indent=2)
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
