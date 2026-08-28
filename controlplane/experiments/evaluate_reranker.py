"""Reranker AND fusion-method comparison: dense-only vs dense+lexical
(min-max weighted-sum vs Reciprocal Rank Fusion) vs each fusion +
cross-encoder -- against the REAL retrieval pipeline and the REAL
30-document corpus (``data/synthetic_enterprise/documents/``), not a
mocked one.

The RRF-vs-min-max comparison (NEW, Milestone 8) exists because
``docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md``
explicitly specifies RRF ("Dense + BM25 + RRF + Cross-Encoder") as the
source-of-truth fusion method -- Milestones 4-7 used min-max weighted-sum
fusion instead, an undocumented deviation found and measured here rather
than silently kept (bootstrap's "architecture contradiction" rule).

Ground truth: ``data/raw/generated/rag_retrieval_relevance_cases.json``
(26 cases, provenance HUMAN -- hand-authored this milestone by reading
all 30 corpus documents directly and writing one query per targeted
document, since ``rag_cases.json``'s inline evidence snippets don't
literally correspond to this corpus -- see
``controlplane/rag/adequacy.py``'s module docstring for that same
limitation). Each case names exactly one relevant source document, so
this measures Recall@1 / Recall@3 / MRR (single-relevant-item ranking
metrics), not graded NDCG.

SMOKE_TEST scale (bootstrap SS40): 26 queries is not a large benchmark.
Stated plainly rather than presented as a large-sample result.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_reranker
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.experiments.metrics import mean_reciprocal_rank, recall_at_k
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.rag.ingestion import _document_title
from controlplane.rag.retrieval import retrieve

_DATASET_PATH = Path("data/raw/generated/rag_retrieval_relevance_cases.json")
DATASET_ID = "rag_retrieval_relevance_cases"
DATASET_VERSION = "v0.1"
_TOP_N = 10  # ranked list depth requested from each config, for a fair rank comparison


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _rank_of(document_name: str, results) -> int | None:
    for i, r in enumerate(results, start=1):
        if r.chunk.document_name == document_name:
            return i
    return None


def _evaluate_config(cases: list[dict], *, dense_weight: float = 0.5, rerank: bool, fusion_method: str = "rrf") -> dict:
    # Warm the lazily-loaded embedding model / cross-encoder singletons
    # (both @lru_cache'd) with one untimed call first -- otherwise the
    # first query's latency absorbs a one-time model-load cost and
    # skews the mean (the same class of measurement bug fixed in
    # Milestone 5's benchmark_real_capability_execution.py).
    cold_start = None
    if cases:
        t0 = time.monotonic()
        retrieve(cases[0]["query"], k=_TOP_N, dense_weight=dense_weight, rerank=rerank, fusion_method=fusion_method)
        cold_start = int((time.monotonic() - t0) * 1000)

    ranks: list[int | None] = []
    latencies_ms: list[int] = []
    for case in cases:
        # Append the real ".txt" suffix before calling _document_title --
        # that function does path.stem.replace("_", " ").title(), and
        # Path.stem only strips one suffix. Filenames like
        # "HR_POLICY_v2.1" contain a dot themselves: wrapping the bare
        # stem in Path(...) directly would make Path.stem misread ".1"
        # as an extension and silently truncate it, breaking the match.
        expected_doc = _document_title(Path(case["relevant_document_stem"] + ".txt"))
        start = time.monotonic()
        results = retrieve(case["query"], k=_TOP_N, dense_weight=dense_weight, rerank=rerank, fusion_method=fusion_method)
        latencies_ms.append(int((time.monotonic() - start) * 1000))
        ranks.append(_rank_of(expected_doc, results))

    return {
        "sample_count": len(cases),
        "recall_at_1": recall_at_k(ranks, 1),
        "recall_at_3": recall_at_k(ranks, 3),
        "mrr": mean_reciprocal_rank(ranks),
        "not_found_count": sum(1 for r in ranks if r is None),
        "cold_start_ms": cold_start,
        "warm_latency_ms_mean": sum(latencies_ms) / len(latencies_ms) if latencies_ms else None,
        "warm_latency_ms_max": max(latencies_ms) if latencies_ms else None,
    }


def main() -> None:
    cases = _load()

    experiment_id = record_experiment(
        experiment_name="rag_reranker_comparison",
        component="rag_retrieval",
        algorithm="dense_vs_fusion_vs_cross_encoder",
        algorithm_version="v1",
    )

    configs = {
        "A_dense_only": dict(dense_weight=1.0, rerank=False, fusion_method="min_max"),
        "B1_dense_plus_lexical_min_max_fusion": dict(dense_weight=0.5, rerank=False, fusion_method="min_max"),
        "B2_dense_plus_lexical_RRF_fusion": dict(rerank=False, fusion_method="rrf"),
        "C1_min_max_plus_cross_encoder": dict(dense_weight=0.5, rerank=True, fusion_method="min_max"),
        "C2_RRF_plus_cross_encoder": dict(rerank=True, fusion_method="rrf"),
    }

    results = {}
    for name, cfg in configs.items():
        metrics = _evaluate_config(cases, **cfg)
        results[name] = metrics
        run_id = record_run(
            experiment_id=experiment_id,
            dataset_id=DATASET_ID,
            dataset_version=DATASET_VERSION,
            model=name,
            configuration=cfg,
            notes="SMOKE_TEST scale (26 hand-authored queries); real retrieval pipeline + real 30-document corpus, not mocked",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)
        print(f"{name}: recall@1={metrics['recall_at_1']:.3f} recall@3={metrics['recall_at_3']:.3f} "
              f"mrr={metrics['mrr']:.3f} cold_start_ms={metrics['cold_start_ms']} "
              f"warm_latency_ms_mean={metrics['warm_latency_ms_mean']:.1f}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"reranker_comparison_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "results": results}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
