"""RAG Adequacy -- "is the retrieved evidence sufficient to answer the
query?" (docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md
SS10-15). Distinct from retrieval relevance: a chunk can be the single
most-relevant thing in the corpus and still not contain enough
information to actually answer the question.

V0 baseline (bootstrap SS18: "evaluate this baseline" -- not required to
reproduce RAGAS/ARES/RAGTruth, only to take a useful mechanism from
them): query-term coverage across the evidence text, optionally combined
with retrieval fusion scores when available. Deterministic, no model
call -- an LLM-judge adequacy evaluator was considered and deferred
(see docs/PROJECT_STATE/DECISIONS.md): this milestone's dataset already
lets a non-LLM baseline be measured meaningfully (docs/EVALUATION/RAG_RESULTS.md),
so bootstrap SS22's "prefer deterministic -> small model -> LLM judge"
ordering says try this first.

Takes evidence as plain text (not tied to ``controlplane.rag.retrieval``'s
``RetrievedChunk``) so it can be evaluated two ways: (1) against this
milestone's real retrieval pipeline, and (2) directly against
``data/raw/generated/rag_cases.json``'s existing (query, evidence,
sufficiency-label) triples -- reusing already-generated data rather than
seeking new/public data, since it already has exactly the labels needed
(bootstrap SS42 requires checking existing data is actually insufficient
before searching for public datasets; here it is not).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "for", "in", "on", "at", "and", "or", "our",
    "we", "what", "how", "does", "do", "did", "can", "could", "should", "would", "with", "this", "that",
    "it", "as", "be", "has", "have", "had", "by", "from", "about", "which", "who", "when",
}


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


_ANY_TOKEN_RE = re.compile("[a-z0-9]+")


def _identifiers(text: str) -> set[str]:
    """Short alphanumeric tokens that NAME a specific entity: 3, q4, v3,
    2024, 501.

    ``_tokenize`` drops every token of two characters or fewer, which was
    meant to remove noise and instead removes the only part of the query
    that distinguishes one entity from another:

        "hotel allowance for Tier 3 cities" -> {allowance, cities, hotel, tier}
        "Q4 revenue for the Americas"       -> {americas, region, revenue}
        "maximum payload size in API v3"    -> {api, maximum, payload, size}

    The quarter, the tier and the version are deleted before scoring, so
    evidence about Tier 1 covers a question about Tier 3 completely. This
    is not a weak signal being outvoted -- the discriminating token is
    gone. Recovering it is a representation fix, not an exception list:
    nothing here mentions any particular tier, quarter or version.
    """
    return {t for t in _ANY_TOKEN_RE.findall(text.lower()) if any(c.isdigit() for c in t)}


def _numeric_aware_tokenize(text: str) -> set[str]:
    """``_tokenize`` plus the identifiers it discards."""
    return _tokenize(text) | _identifiers(text)


def _identifier_keys(text: str) -> set[str]:
    """Identifiers bound to the word they qualify.

    A bare identifier set is a bag, and a bag matches by accident. Asking
    for the Tier 2 allowance against a chunk headed "Travel Policy 4.2"
    finds "2" in the evidence -- in a section number -- and concludes the
    evidence is about Tier 2. Retrieving MORE chunks makes that worse,
    because every extra section heading contributes more stray digits.

    So a short bare number is keyed to the informative word before it:
    "tier 3", not "3". An identifier that already carries letters (q4,
    v3) or is long enough to be specific on its own (250, 2024, 501)
    names its entity without help and is kept as-is.

    This is a refinement of the representation, not an exception list: it
    mentions no particular tier, quarter or version, and it is what makes
    "tier 3" absent from a corpus in which "tier 1" is present.
    """
    tokens = _TOKEN_RE.findall(text.lower())
    keys: set[str] = set()
    for i, token in enumerate(tokens):
        if not any(c.isdigit() for c in token):
            continue
        if len(token) > 2 or not token.isdigit():
            keys.add(token)
            continue
        context = next(
            (t for t in reversed(tokens[:i])
             if t not in _STOPWORDS and len(t) > 2 and not any(c.isdigit() for c in t)),
            None,
        )
        keys.add(f"{context} {token}" if context else token)
    return keys


class AdequacyLabel(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    PARTIALLY_SUFFICIENT = "PARTIALLY_SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"
    """Structurally supported, but see docs/EVALUATION/RAG_RESULTS.md:
    data/raw/generated/rag_cases.json has no ground-truth example with
    this label (its adequacy field only ever takes the other three
    values) -- so this branch is exercised by a synthetic unit test, not
    validated against real labeled data. Stated plainly, not hidden."""


@dataclass
class AdequacyResult:
    label: AdequacyLabel
    coverage: float
    """Fraction of the query's informative (non-stopword) terms that
    appear somewhere in the evidence text -- the primary signal."""
    reason: str
    source: str = "coverage_overlap_v0"


class RAGAdequacyEvaluator:
    name = "coverage_overlap_v0"

    def __init__(
        self,
        sufficient_threshold: float = 0.32,
        partial_threshold: float = 0.05,
        numeric_aware_tokens: bool = True,
        require_identifier_match: bool = True,
    ) -> None:
        """Defaults calibrated via grid search against
        ``data/raw/generated/rag_cases.json`` (150 examples) --
        accuracy 0.80, macro-F1 0.774, up from 0.493/0.521 at the
        initially-guessed 0.5/0.2 thresholds. No separate held-out split
        exists for this calibration (the dataset is used both to
        calibrate and to report the resulting metric) -- a real
        limitation, stated per docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md
        SS32's "select threshold using a validation dataset" guidance,
        which this only partially satisfies. See
        docs/EVALUATION/RAG_RESULTS.md.

        DEFAULTS CHANGED 2026-08-30 on held-out evidence. The two token
        flags default ON. Measured on
        ``rag_adequacy_semantic_cases.json`` (32 dev / 32 test, tuned on
        dev and scored once on test):

            condition       test macro-F1   false confidence   guard
            A (old default)     0.382             0.929        0.866
            C (new default)     0.515             0.714        0.871

        "False confidence" is the rate at which evidence about a
        DIFFERENT entity was called SUFFICIENT. The old default did that
        on 13 of 14 held-out absence cases, which is the mechanism behind
        the 64% confabulation rate measured on adjacent-evidence
        unanswerable queries.

        "Guard" is macro-F1 on ``rag_cases.json`` (150), the distribution
        these thresholds were originally calibrated on: the change costs
        nothing there and is fractionally better.

        A semantic variant scored higher still on the new set (macro-F1
        0.648, false confidence 0.429) and was REJECTED: it fell to 0.690
        on the guard, a 17-point regression on the main RAG path. See
        docs/PROJECT_STATE/DECISIONS.md."""
        self._sufficient = sufficient_threshold
        self._partial = partial_threshold
        self._numeric_aware = numeric_aware_tokens
        self._require_identifier_match = require_identifier_match
        """When set, an identifier named in the QUERY but absent from ALL
        evidence forces INSUFFICIENT regardless of coverage.

        The claim being encoded is narrow and checkable: evidence that
        never mentions the entity the question names is evidence about a
        different entity. It says nothing about which tiers, quarters or
        versions exist."""

    def assess(self, query: str, evidence_texts: list[str]) -> AdequacyResult:
        if not evidence_texts or all(not t.strip() for t in evidence_texts):
            return AdequacyResult(AdequacyLabel.INSUFFICIENT, 0.0, "no evidence retrieved")

        tokenize = _numeric_aware_tokenize if self._numeric_aware else _tokenize
        query_terms = tokenize(query)
        if not query_terms:
            return AdequacyResult(AdequacyLabel.INSUFFICIENT, 0.0, "query had no scorable terms")

        evidence_terms: set[str] = set()
        per_doc_overlap = []
        for text in evidence_texts:
            terms = tokenize(text)
            overlap = query_terms & terms
            per_doc_overlap.append(len(overlap) / len(query_terms))
            evidence_terms |= terms

        coverage = len(query_terms & evidence_terms) / len(query_terms)

        # A crude, explicitly-limited conflict signal: two (or more)
        # evidence items each independently covering a meaningful share
        # of the query but disagreeing on a polarity-flipping word pair
        # -- checked only for this one common pattern (not a general
        # contradiction detector).
        #
        # Regression (found via Milestone 6's mandatory architecture
        # audit, real end-to-end trace of the RAG self-healing scenario
        # at a widened retry k): a naive ``pos in text`` substring check
        # matched "not" inside the unrelated word "notice" (HR Policy's
        # "Resignation **not**ice is 30 days"), so two completely
        # unrelated documents -- one containing "must", the other just
        # containing the word "notice" -- were flagged as CONFLICTING
        # even though neither is actually about the query or about each
        # other. Same root cause as Milestone 3's actionability
        # false-positive: a keyword-presence check with no word-boundary
        # awareness. Fixed the same way: match whole words only.
        _POLARITY_PAIRS = [
            ("required", "optional"), ("mandatory", "optional"), ("mandatory", "exempt"),
            ("allowed", "prohibited"), ("must", "not"),
        ]
        conflicting = False
        if len(evidence_texts) > 1:
            lowered = [t.lower() for t in evidence_texts]
            for pos, neg in _POLARITY_PAIRS:
                pos_re, neg_re = re.compile(rf"\b{re.escape(pos)}\b"), re.compile(rf"\b{re.escape(neg)}\b")
                has_pos = any(pos_re.search(t) for t in lowered)
                has_neg = any(neg_re.search(t) for t in lowered)
                if has_pos and has_neg:
                    conflicting = True
                    break

        missing_identifiers: set[str] = set()
        if self._require_identifier_match:
            evidence_identifiers: set[str] = set()
            for text in evidence_texts:
                evidence_identifiers |= _identifier_keys(text)
            missing_identifiers = _identifier_keys(query) - evidence_identifiers

        if missing_identifiers and not conflicting:
            return AdequacyResult(
                AdequacyLabel.INSUFFICIENT,
                coverage,
                f"evidence never mentions {sorted(missing_identifiers)} named by the query "
                f"(term coverage={coverage:.2f} -- the evidence is about a different entity)",
            )

        if conflicting:
            label = AdequacyLabel.CONFLICTING
            reason = f"evidence items disagree on a polarity term (coverage={coverage:.2f})"
        elif coverage >= self._sufficient:
            label = AdequacyLabel.SUFFICIENT
            reason = f"query-term coverage={coverage:.2f} across {len(evidence_texts)} evidence item(s)"
        elif coverage >= self._partial:
            label = AdequacyLabel.PARTIALLY_SUFFICIENT
            reason = f"partial query-term coverage={coverage:.2f} across {len(evidence_texts)} evidence item(s)"
        else:
            label = AdequacyLabel.INSUFFICIENT
            reason = f"low query-term coverage={coverage:.2f} across {len(evidence_texts)} evidence item(s)"

        return AdequacyResult(label=label, coverage=coverage, reason=reason)
