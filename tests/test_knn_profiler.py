"""Requires the local embedding model to already be cached (see
controlplane/models/model_download.py) -- these tests never hit the
network themselves; they only load from the local Hugging Face cache."""

from controlplane.query_intelligence.fingerprint import CapabilityHint
from controlplane.query_intelligence.knn_profiler import EmbeddingKNNQueryProfiler, HybridQueryProfiler
from controlplane.query_intelligence.rules import RuleBasedQueryProfiler


def test_knn_profiler_returns_a_valid_fingerprint():
    fp = EmbeddingKNNQueryProfiler(k=5).profile("What was our Q4 revenue compared to last year?")
    assert fp.source == "embedding_knn"
    assert fp.domain is not None
    assert "nearest_match" in fp.confidence
    assert 0.0 <= fp.confidence["nearest_match"] <= 1.0
    assert fp.capability_hints  # never empty -- GENERAL is the floor


def test_knn_profiler_confidence_reflects_similarity_not_a_fabricated_value():
    fp = EmbeddingKNNQueryProfiler(k=5).profile("What was our Q4 revenue compared to last year?")
    # A near-duplicate of a real exemplar query should score high similarity.
    assert fp.confidence["nearest_match"] > 0.5


def test_hybrid_profiler_prefers_rule_when_a_rule_confidently_fires():
    fp = HybridQueryProfiler().profile("Please execute a refund for this customer.")
    assert "actionability" in RuleBasedQueryProfiler().profile("Please execute a refund for this customer.").high_confidence_fields
    assert fp.actionability.value == "agentic"
    assert CapabilityHint.AGENT in fp.capability_hints


def test_hybrid_profiler_unions_capability_hints_from_both_methods():
    fp = HybridQueryProfiler().profile("What was our Q4 revenue?")
    rule_hints = set(RuleBasedQueryProfiler().profile("What was our Q4 revenue?").capability_hints)
    assert rule_hints.issubset(set(fp.capability_hints))


def test_hybrid_profiler_defers_to_knn_for_complexity_since_rules_word_count_is_never_high_confidence():
    query = "Given our recent SOC 2 audit findings, should we adopt an IGA tool?"
    rule_fp = RuleBasedQueryProfiler().profile(query)
    hybrid_fp = HybridQueryProfiler().profile(query)
    assert "complexity" not in rule_fp.high_confidence_fields
    # Hybrid's complexity must come from knn, not from the rules' word-count
    # fallback, whenever they'd disagree -- verified by construction here:
    # the picked value must equal the knn baseline's independent output.
    knn_fp = EmbeddingKNNQueryProfiler().profile(query)
    assert hybrid_fp.complexity == knn_fp.complexity


def test_no_confident_trigger_fields_are_ever_fabricated_as_confident():
    # A query with zero keyword matches at all should have an empty
    # high_confidence_fields list -- nothing to trust blindly.
    fp = RuleBasedQueryProfiler().profile("hi")
    assert fp.high_confidence_fields == []
