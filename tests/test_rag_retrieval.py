from controlplane.rag.ingestion import load_chunks
from controlplane.rag.retrieval import BM25, retrieve


def test_load_chunks_returns_all_documents():
    chunks = load_chunks()
    assert len(chunks) >= 30  # at least one chunk per document
    assert all(c.embedding.shape == (384,) for c in chunks)


def test_retrieve_finds_the_relevant_document_for_a_direct_policy_question():
    results = retrieve("What is our refund policy for cancelled subscriptions?", k=3)
    assert results
    assert results[0].chunk.document_name == "Customer Refund Policy"
    assert results[0].fused_score == max(r.fused_score for r in results)


def test_retrieve_respects_k():
    results = retrieve("policy", k=2)
    assert len(results) == 2


def test_bm25_scores_exact_term_match_higher_than_no_match():
    bm25 = BM25([["refund", "policy", "subscription"], ["security", "incident", "response"]])
    scores = bm25.scores_for_query(["refund"])
    assert scores[0] > scores[1]


def test_bm25_empty_query_returns_zero_scores():
    bm25 = BM25([["a", "b"], ["c", "d"]])
    assert bm25.scores_for_query([]) == [0.0, 0.0]
