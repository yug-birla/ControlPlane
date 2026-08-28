"""RAG capability -- wires ``controlplane.rag.retrieval`` (dense + BM25 +
score fusion) and ``controlplane.rag.adequacy`` (SUFFICIENT/PARTIAL/
INSUFFICIENT/CONFLICTING) into one capability the ``GraphExecutor`` can
invoke for a ``RAG`` node, replacing the ``MOCKED`` handler used through
Milestone 3.
"""

from __future__ import annotations

from controlplane.rag.adequacy import RAGAdequacyEvaluator
from controlplane.rag.retrieval import retrieve


class RAGCapability:
    name = "rag_v0_dense_bm25_fusion"

    def __init__(self, k: int = 5) -> None:
        self._k = k
        self._adequacy = RAGAdequacyEvaluator()

    def execute(self, query_text: str, k: int | None = None) -> dict:
        """``k`` overrides the constructor default for a single call --
        used by the Intervention Engine's RETRIEVE_MORE mechanism
        (controlplane/intervention/engine.py) to retry with a wider
        candidate set without constructing a second ``RAGCapability``."""
        results = retrieve(query_text, k=k or self._k)
        evidence_texts = [r.chunk.text for r in results]
        adequacy = self._adequacy.assess(query_text, evidence_texts)

        return {
            "status": "EXECUTED",
            "retrieved_count": len(results),
            "evidence": [
                {
                    "document": r.chunk.document_name,
                    "text": r.chunk.text,
                    "dense_score": r.dense_score,
                    "lexical_score": r.lexical_score,
                    "fused_score": r.fused_score,
                }
                for r in results
            ],
            "adequacy": {"label": adequacy.label.value, "coverage": adequacy.coverage, "reason": adequacy.reason},
            "source": "synthetic_enterprise/documents (30 internal policy documents)",
        }
