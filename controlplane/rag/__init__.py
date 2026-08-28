"""Real RAG pipeline -- Milestone 4 (the "next major build" bootstrap).

DOCUMENTS -> ingestion/chunking -> embeddings -> dense + lexical
retrieval -> score-fusion merge ("reranking", V0) -> evidence package
-> adequacy assessment. See docs/ALGORITHMS/RAG_PIPELINE.md and
docs/EVALUATION/RAG_RESULTS.md.
"""
