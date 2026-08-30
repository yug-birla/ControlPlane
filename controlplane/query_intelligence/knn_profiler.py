"""Baseline B: embedding k-NN Query Profiler, and the Hybrid profiler that
combines it with Baseline A (rules).

Method: encode the query with the local embedding model
(``controlplane.models.local_hf_provider``), find the k nearest exemplars
in the train split by cosine similarity, and majority-vote each field
directly from the fields those exemplars already carry. No training step
-- the "model" is the frozen embedding function plus the existing labeled
data, which is exactly why this needs no fine-tuning to exist (bootstrap
SS21: fine-tune only when a measured gap justifies it).
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from controlplane.query_intelligence.exemplar_bank import Exemplar, load_exemplars, nearest


@lru_cache(maxsize=1)
def _embedding_provider():
    """Load the local embedding model once per process, not once per
    request -- a fresh SentenceTransformer() call reloads weights from
    disk every time (~2s), which is fine for a script but wrong for a
    profiler called per-query."""
    from controlplane.models.local_hf_provider import LocalHFEmbeddingProvider

    return LocalHFEmbeddingProvider()
from controlplane.query_intelligence.fingerprint import (
    Actionability,
    Ambiguity,
    CapabilityHint,
    Complexity,
    DataRequirement,
    Impact,
    Intent,
    QueryFingerprint,
    Sensitivity,
)
from controlplane.query_intelligence.rules import RuleBasedQueryProfiler

_TAXONOMY_TO_CAPABILITY = {
    "SQL": CapabilityHint.SQL,
    "RAG": CapabilityHint.RAG,
    "INSUFFICIENT_RAG": CapabilityHint.RAG,
    "MEMORY": CapabilityHint.MEMORY,
    "CHAT_HISTORY": CapabilityHint.CHAT_HISTORY,
    "REASONING": CapabilityHint.REASONING,
    "CODING": CapabilityHint.CODING,
    "AGENTIC": CapabilityHint.AGENT,
    "HIGH_RISK_AGENTIC": CapabilityHint.AGENT,
    "MULTI_SOURCE": CapabilityHint.MULTI_SOURCE,
}

# Partial reconciliation of the granular, unreconciled required_data_sources
# vocabulary (docs/PROJECT_STATE/BLOCKERS.md B6) onto the canonical
# docs/DATA/SOURCES_AND_CAPABILITIES.md values. Only maps values with an
# unambiguous match; anything else is dropped rather than guessed.
_SOURCE_TO_CANONICAL = {
    "public_knowledge": DataRequirement.WEB_SEARCH,
    "memory_store": DataRequirement.MEMORY_STORE,
    "conversation_history": DataRequirement.CHAT_DATABASE,
    "internal_document_store": DataRequirement.RAG_CORPUS,
    "internal_policy_documents": DataRequirement.RAG_CORPUS,
    "internal_corporate_records": DataRequirement.RAG_CORPUS,
    "internal_contract_documents": DataRequirement.RAG_CORPUS,
    "internal_strategy_documents": DataRequirement.RAG_CORPUS,
    "internal_product_roadmap": DataRequirement.RAG_CORPUS,
    "internal_rfp_documents": DataRequirement.RAG_CORPUS,
    "market_research_documents": DataRequirement.RAG_CORPUS,
    "enterprise_document_management_system": DataRequirement.RAG_CORPUS,
}


def _reconcile_source(raw: str) -> DataRequirement | None:
    if raw in _SOURCE_TO_CANONICAL:
        return _SOURCE_TO_CANONICAL[raw]
    if "database" in raw or "_system" in raw and "document" not in raw:
        return DataRequirement.SQL_DB
    return None


def _majority(values: list[str]) -> str:
    return Counter(values).most_common(1)[0][0]


def _actionability_to_intent(actionability: Actionability, taxonomy: set[str]) -> Intent:
    if actionability == Actionability.AGENTIC:
        return Intent.AGENTIC_WORKFLOW if "HIGH_RISK_AGENTIC" in taxonomy else Intent.ACTION_REQUEST
    if "REASONING" in taxonomy:
        return Intent.REASONING
    if "RECOMMENDATION" in taxonomy:
        return Intent.RECOMMENDATION
    if "DECISION_SUPPORT" in taxonomy:
        return Intent.DECISION_SUPPORT
    if "CODING" in taxonomy:
        return Intent.GENERATION
    if "MEMORY" in taxonomy or "CHAT_HISTORY" in taxonomy:
        return Intent.CONVERSATIONAL_PERSONAL
    if "ANALYTICAL" in taxonomy:
        return Intent.ANALYTICAL
    return Intent.FACTUAL_LOOKUP


class EmbeddingKNNQueryProfiler:
    name = "embedding_knn"

    def __init__(
        self,
        k: int = 5,
        agentic_escalation_threshold: float | None = None,
    ) -> None:
        self._k = k
        self._agentic_tau = agentic_escalation_threshold
        """Similarity-weighted share of neighbours labelled ``agentic``
        above which actionability is escalated to AGENTIC regardless of
        the majority vote. ``None`` keeps plain majority behaviour.

        WHY A SEPARATE RULE FOR THIS ONE FIELD. Majority voting treats
        every misclassification as equally costly. For actionability that
        is false: actionability decides whether CapabilityHint.AGENT is
        selected, which decides whether an actor agent exists, which
        decides whether AgentGate runs and whether CompositionGovernor
        has a chain to inspect. Scoring an action as informational does
        not merely mislabel it -- it removes the agent governance layer
        from that request. Scoring an informational query as an action
        costs one gate evaluation.

        The losses are asymmetric, so the aggregator should be too. This
        is the same shape of fix as the domain-aware injection
        thresholds (DECISIONS.md, C6): keep the representation, change
        the decision rule to reflect what a miss actually costs.
        """

    def profile(self, query: str) -> QueryFingerprint:
        import numpy as np

        embedding = _embedding_provider().embed(text=query).embedding
        results = nearest(np.array(embedding, dtype="float32"), k=self._k)
        return self._fingerprint_from_neighbors(results)

    def _fingerprint_from_neighbors(self, results: list[tuple[Exemplar, float]]) -> QueryFingerprint:
        neighbors = [ex for ex, _ in results]
        top_sim = results[0][1] if results else 0.0
        avg_sim = sum(s for _, s in results) / len(results) if results else 0.0

        complexity = Complexity(_majority([n.complexity for n in neighbors]))
        sensitivity = Sensitivity(_majority([n.sensitivity for n in neighbors]))
        ambiguity = Ambiguity(_majority([n.ambiguity for n in neighbors]))
        actionability = Actionability(_majority([n.actionability for n in neighbors]))
        if self._agentic_tau is not None and results:
            total = sum(max(sim, 0.0) for _, sim in results) or 1e-9
            agentic_weight = sum(
                max(sim, 0.0) for ex, sim in results if ex.actionability == "agentic"
            )
            # A sensitivity-conditioned variant was considered and
            # rejected without spending a run on it: all 10 agentic
            # exemplars in the train split carry sensitivity NONE, so
            # gating escalation on a sensitivity signal would suppress
            # it on every action. Sensitivity labels DATA EXPOSURE in
            # this dataset; it is orthogonal to action risk.
            if agentic_weight / total >= self._agentic_tau:
                actionability = Actionability.AGENTIC
        domain = neighbors[0].domain  # highest-cardinality field: nearest single neighbor, not a vote

        label_counts = Counter(label for n in neighbors for label in n.taxonomy_labels)
        majority_labels = {label for label, count in label_counts.items() if count > len(neighbors) / 2}
        capability_hints = sorted({_TAXONOMY_TO_CAPABILITY[l] for l in majority_labels if l in _TAXONOMY_TO_CAPABILITY}, key=lambda h: h.value)
        if not capability_hints:
            capability_hints = [CapabilityHint.GENERAL]

        source_counts = Counter(s for n in neighbors for s in n.required_data_sources)
        data_requirement = sorted(
            {r for r in (_reconcile_source(s) for s in source_counts) if r is not None},
            key=lambda d: d.value,
        )

        intent = _actionability_to_intent(actionability, majority_labels)
        impact = Impact.HIGH if actionability == Actionability.AGENTIC else Impact.LOW

        nearest_ids = ", ".join(f"{n.query_id}({sim:.2f})" for n, sim in results)
        explanation = {
            "complexity": f"majority vote among top-{len(neighbors)} exemplars [{nearest_ids}]",
            "sensitivity": f"majority vote among top-{len(neighbors)} exemplars",
            "ambiguity": f"majority vote among top-{len(neighbors)} exemplars",
            "actionability": f"majority vote among top-{len(neighbors)} exemplars",
            "domain": f"nearest exemplar {neighbors[0].query_id!r}: {domain!r}",
            "capability_hints": f"taxonomy labels appearing in >50% of top-{len(neighbors)} exemplars: {sorted(majority_labels)}",
            "intent": f"derived from actionability={actionability.value} and taxonomy labels {sorted(majority_labels)} (not evaluated against ground truth)",
        }

        return QueryFingerprint(
            intent=intent,
            domain=domain,
            data_requirement=data_requirement,
            complexity=complexity,
            sensitivity=sensitivity,
            ambiguity=ambiguity,
            impact=impact,
            actionability=actionability,
            capability_hints=capability_hints,
            confidence={"complexity": avg_sim, "sensitivity": avg_sim, "actionability": avg_sim, "nearest_match": top_sim},
            explanation=explanation,
            source=self.name,
        )


class HybridQueryProfiler:
    """Rules first (trusted at face value where they fire); embedding k-NN
    fills every field rules didn't confidently resolve. List-valued fields
    (capability_hints, data_requirement) are unioned rather than replaced,
    since more corroborating evidence is strictly more useful there."""

    name = "hybrid"

    def __init__(
        self,
        k: int = 5,
        use_corpus_affinity: bool = True,
        agentic_escalation_threshold: float | None = None,
    ) -> None:
        self._rules = RuleBasedQueryProfiler()
        self._knn = EmbeddingKNNQueryProfiler(
            k=k, agentic_escalation_threshold=agentic_escalation_threshold
        )
        self._use_corpus_affinity = use_corpus_affinity
        self._agentic_tau = agentic_escalation_threshold

    def _corpus_affinity_hint(self, query: str, explanation: dict) -> bool:
        """Milestone 9: does the real corpus actually contain something
        relevant to this query?

        The keyword rule produced ``CapabilityHint.RAG`` only for seven
        literal words, giving measured recall of 0.053 on
        corpus-answerable questions -- so ControlPlane almost never
        retrieved and returned the same answer as an unmanaged model.
        Adding more keywords cannot fix a representation problem, so this
        asks the semantic question directly. See
        ``controlplane.query_intelligence.corpus_affinity``.
        """
        if not self._use_corpus_affinity:
            return False
        try:
            from controlplane.query_intelligence.corpus_affinity import (
                get_corpus_affinity_detector,
            )

            detector = get_corpus_affinity_detector()
            affinity = detector.assess(query)
        except Exception:
            # Never fail a request because the corpus/embeddings are
            # unavailable -- degrade to the keyword behaviour, same
            # graceful-degradation pattern as the injection k-NN layer.
            return False

        if affinity.is_corpus_answerable:
            explanation["capability_hints_corpus_affinity"] = (
                f"corpus affinity {affinity.max_similarity:.3f} >= "
                f"{detector.threshold:.2f} "
                f"(nearest: {affinity.nearest_document})"
            )
            return True
        return False

    def profile(self, query: str) -> QueryFingerprint:
        rule_fp = self._rules.profile(query)
        knn_fp = self._knn.profile(query)

        explanation = dict(knn_fp.explanation)
        explanation.update(rule_fp.explanation)  # rule explanations win where both exist

        def pick(field: str, rule_val, knn_val):
            # Only trust the rule's value when a specific trigger actually
            # fired for this field -- not merely because the rules baseline
            # always produces *some* value (e.g. complexity's word-count
            # default). See fingerprint.py's high_confidence_fields docstring
            # and docs/PROJECT_STATE/DECISIONS.md for why this replaced a
            # naive "field in rule_fp.explanation" check (every field always
            # has an explanation, even the weak fallback ones).
            return rule_val if field in rule_fp.high_confidence_fields else knn_val

        merged_hints = {
            h for h in (*rule_fp.capability_hints, *knn_fp.capability_hints)
            if h != CapabilityHint.GENERAL
        }
        merged_sources = {*rule_fp.data_requirement, *knn_fp.data_requirement}

        # Semantic RAG layer, consulted only when neither the keyword
        # rules nor the k-NN neighbours already asked for retrieval
        # (deterministic-first / semantic-fallback -- the same layering
        # used by PromptInjectionEvaluator).
        if CapabilityHint.RAG not in merged_hints and self._corpus_affinity_hint(query, explanation):
            merged_hints.add(CapabilityHint.RAG)
            merged_sources.add(DataRequirement.RAG_CORPUS)

        capability_hints = sorted(merged_hints or {CapabilityHint.GENERAL}, key=lambda h: h.value)
        data_requirement = sorted(merged_sources, key=lambda d: d.value)

        confidence = dict(knn_fp.confidence)
        confidence.update(rule_fp.confidence)

        return QueryFingerprint(
            intent=pick("intent", rule_fp.intent, knn_fp.intent),
            domain=knn_fp.domain,
            data_requirement=data_requirement,
            complexity=pick("complexity", rule_fp.complexity, knn_fp.complexity),
            sensitivity=pick("sensitivity", rule_fp.sensitivity, knn_fp.sensitivity),
            ambiguity=pick("ambiguity", rule_fp.ambiguity, knn_fp.ambiguity),
            impact=pick("impact", rule_fp.impact, knn_fp.impact),
            actionability=pick("actionability", rule_fp.actionability, knn_fp.actionability),
            capability_hints=capability_hints,
            confidence=confidence,
            explanation=explanation,
            high_confidence_fields=rule_fp.high_confidence_fields,
            source=self.name,
        )
