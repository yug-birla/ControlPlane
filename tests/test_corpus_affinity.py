"""Corpus-affinity RAG routing tests.

The detector's whole job is a real semantic judgement against the real
corpus, so these use the real embedding model and the real corpus
chunks (both already cached, and already exercised by
tests/test_rag_retrieval.py) rather than faking the thing under test
into vacuity.
"""

from __future__ import annotations

from controlplane.query_intelligence.corpus_affinity import CorpusAffinityDetector
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler


def test_corpus_answerable_question_without_any_rag_keyword_is_detected():
    """Regression for the Milestone 9 P0 finding: this exact question
    contains none of the seven keywords the old rule required
    ("policy", "document", "manual", ...), so the keyword-only router
    produced GENERAL, no RAG node was created, no retrieval happened,
    and ControlPlane returned the same answer as an unmanaged model."""
    affinity = CorpusAffinityDetector().assess(
        "What is our hotel allowance per night for Tier 1 cities?"
    )
    assert affinity.is_corpus_answerable
    assert affinity.nearest_document == "Travel Policy 2024"


def test_general_knowledge_question_is_not_routed_to_retrieval():
    """The corpus has nothing to say about this, so retrieving would be
    wasted latency -- precision matters as much as recall here."""
    affinity = CorpusAffinityDetector().assess(
        "Who wrote the novel One Hundred Years of Solitude?"
    )
    assert not affinity.is_corpus_answerable


def test_affinity_reports_the_similarity_it_decided_on():
    """The score is surfaced for auditability -- a routing decision that
    can't be explained is not much better than a keyword list."""
    affinity = CorpusAffinityDetector().assess("How many days of paid sick leave do we get?")
    assert 0.0 <= affinity.max_similarity <= 1.0
    assert affinity.nearest_document is not None


def test_threshold_is_respected():
    query = "What is our hotel allowance per night for Tier 1 cities?"
    assert CorpusAffinityDetector(similarity_threshold=0.05).assess(query).is_corpus_answerable
    assert not CorpusAffinityDetector(similarity_threshold=0.99).assess(query).is_corpus_answerable


def test_hybrid_profiler_emits_the_rag_hint_from_corpus_affinity_alone():
    """End-to-end through the profiler the Runtime actually uses -- the
    detector working in isolation was never the problem."""
    fingerprint = HybridQueryProfiler().profile(
        "What is the home office equipment stipend for new hires?"
    )
    assert any(h.value == "RAG" for h in fingerprint.capability_hints)
    assert any(d.value == "RAG_CORPUS" for d in fingerprint.data_requirement)


def test_hybrid_profiler_can_disable_corpus_affinity_for_ablation():
    """The ablation study needs the Milestone 8 behaviour reproducible on
    demand (controlplane/experiments/evaluate_ablations.py condition B)."""
    query = "What is the home office equipment stipend for new hires?"
    without = HybridQueryProfiler(use_corpus_affinity=False).profile(query)
    assert not any(h.value == "RAG" for h in without.capability_hints)
