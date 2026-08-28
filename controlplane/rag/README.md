# controlplane/rag/

**Purpose:** real RAG pipeline — ingestion/chunking, dense+lexical retrieval with score fusion, a real cross-encoder reranking stage, adequacy assessment. See `docs/ALGORITHMS/RAG_PIPELINE.md` and `docs/EVALUATION/RAG_RESULTS.md`.

## Interface

- `ingestion.py`: `load_chunks() -> list[Chunk]` — reads `data/synthetic_enterprise/documents/`, chunks, embeds (disk-cached).
- `retrieval.py`: `retrieve(query, k, rerank=False) -> list[RetrievedChunk]` (dense + BM25 + fusion, optionally reranked), `BM25` (from-scratch, no dependency).
- `reranker.py`: `CrossEncoderReranker.rerank(query, candidates, top_k) -> list[RetrievedChunk]` — `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- `adequacy.py`: `RAGAdequacyEvaluator.assess(query, evidence_texts) -> AdequacyResult` (incl. `CONFLICTING`, now word-boundary-matched — see Limitations).

Wired as a real capability by `controlplane/capabilities/rag_capability.py` (`use_reranker=True` by default), not called directly by the runtime.

## Dependencies

`controlplane.models.local_hf_provider` (embeddings), `controlplane.models.embedding_cache` (disk cache), `sentence_transformers.CrossEncoder` (reranker, lazy-imported).

## Limitations

Score fusion (0.5/0.5) is not tuned. Cross-encoder reranking adds ~1.1s/query on CPU (measured, see `docs/EVALUATION/RAG_RESULTS.md`). Relevance ground truth for the real 30-document corpus is a 26-case hand-authored SMOKE_TEST set, not exhaustive.

## Extension points

`retrieve(..., rerank=True)` is the two-stage retrieve-then-rerank pattern; a different reranker model would only need a new class matching `CrossEncoderReranker`'s `.rerank(query, candidates, top_k)` interface.
