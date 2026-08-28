# controlplane/rag/

**Purpose:** real RAG pipeline — ingestion/chunking, dense+lexical retrieval with score fusion, adequacy assessment. See `docs/ALGORITHMS/RAG_PIPELINE.md` and `docs/EVALUATION/RAG_RESULTS.md`.

## Interface

- `ingestion.py`: `load_chunks() -> list[Chunk]` — reads `data/synthetic_enterprise/documents/`, chunks, embeds (disk-cached).
- `retrieval.py`: `retrieve(query, k) -> list[RetrievedChunk]` (dense + BM25 + fusion), `BM25` (from-scratch, no dependency).
- `adequacy.py`: `RAGAdequacyEvaluator.assess(query, evidence_texts) -> AdequacyResult`.

Wired as a real capability by `controlplane/capabilities/rag_capability.py`, not called directly by the runtime.

## Dependencies

`controlplane.models.local_hf_provider` (embeddings), `controlplane.models.embedding_cache` (disk cache).

## Limitations

Score fusion (0.5/0.5) is not tuned. No cross-encoder reranker. No relevance ground truth for the real 30-document corpus.

## Extension points

A cross-encoder reranker slots in between `retrieve()`'s fusion step and the caller without changing the `RetrievedChunk` shape.
