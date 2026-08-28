"""RAG capability -- wires ``controlplane.rag.retrieval`` (dense + BM25
fusion candidate generation, then a real cross-encoder reranking stage)
and ``controlplane.rag.adequacy`` (SUFFICIENT/PARTIAL/INSUFFICIENT/
CONFLICTING) into one capability the ``GraphExecutor`` can invoke for a
``RAG`` node, replacing the ``MOCKED`` handler used through Milestone 3.

``use_reranker`` defaults to ``True``: the cross-encoder is a real, live
stage in the actual runtime path, not unused/decorative infrastructure
(see docs/EVALUATION/RAG_RESULTS.md for the measured reranker gain, and
``controlplane.rag.reranker`` for the model). Kept as a constructor flag
(not hard-wired) so ``controlplane/experiments/evaluate_reranker.py`` can
run the same capability with it off for a fair before/after comparison.
"""

from __future__ import annotations

from controlplane.rag.adequacy import RAGAdequacyEvaluator
from controlplane.rag.retrieval import retrieve


class RAGCapability:
    name = "rag_v1_dense_bm25_cross_encoder"

    def __init__(self, k: int = 5, use_reranker: bool = True) -> None:
        self._k = k
        self._use_reranker = use_reranker
        self._adequacy = RAGAdequacyEvaluator()

    def execute(self, query_text: str, k: int | None = None) -> dict:
        """``k`` overrides the constructor default for a single call --
        used by the Intervention Engine's RETRIEVE_MORE mechanism
        (controlplane/intervention/engine.py) to retry with a wider
        candidate set without constructing a second ``RAGCapability``."""
        results = retrieve(query_text, k=k or self._k, rerank=self._use_reranker)
        evidence_texts = [r.chunk.text for r in results]
        adequacy = self._adequacy.assess(query_text, evidence_texts)

        return {
            "status": "EXECUTED",
            "retrieved_count": len(results),
            "reranked": self._use_reranker,
            "evidence": [
                {
                    "document": r.chunk.document_name,
                    "text": r.chunk.text,
                    "dense_score": r.dense_score,
                    "lexical_score": r.lexical_score,
                    "fused_score": r.fused_score,
                    "cross_encoder_score": r.cross_encoder_score,
                }
                for r in results
            ],
            "adequacy": {"label": adequacy.label.value, "coverage": adequacy.coverage, "reason": adequacy.reason},
            "source": "synthetic_enterprise/documents (30 internal policy documents)",
        }
