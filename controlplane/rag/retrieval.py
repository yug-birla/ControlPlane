"""Dense + lexical retrieval, fusion, and a real cross-encoder reranking
stage.

Baseline choice (per bootstrap SS17/SS50/SS51 -- "choose a small
practical baseline," "do not implement every paper"):

- Dense: cosine similarity over the local embedding model's vectors
  (same model as the Query Profiler's k-NN baseline).
- Lexical: BM25, implemented from scratch (~40 lines) rather than adding
  a dependency -- consistent with this codebase's existing
  dependency-free-metrics precedent (``controlplane/experiments/metrics.py``).
- Fusion: **Reciprocal Rank Fusion (RRF)** -- the default, per
  ``docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md``
  SS"Reciprocal Rank Fusion" / SS198's explicit "Dense + BM25 + RRF +
  Cross-Encoder" contract (Cormack, Clarke & Büttcher). Milestone 4/5/6/7
  used min-max-normalized weighted-sum fusion instead -- a real,
  undocumented deviation from the source-of-truth spec, found and fixed
  in Milestone 8 (bootstrap's own "architecture contradiction" rule:
  fix it or report it, don't silently keep it) after measuring RRF
  against it (`docs/EVALUATION/RAG_RESULTS.md`) and finding no evidence
  favoring the deviation. ``fusion_method="min_max"`` is kept available
  (not deleted) for that comparison and for anyone reproducing the
  earlier milestones' exact numbers.

A real cross-encoder (``controlplane.rag.reranker``) reranks the fused
candidates when ``rerank=True``. ``retrieve()`` defaults to
``rerank=False`` (unchanged behavior for existing callers/tests);
``RAGCapability`` -- the path actually used by the runtime -- passes
``rerank=True`` so the cross-encoder is a real, live stage, not
decorative unused code.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from controlplane.rag.ingestion import Chunk, load_chunks

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
    return float(np.dot(a, b) / denom)


class BM25:
    """Standard Okapi BM25 (Robertson & Walker), k1=1.5, b=0.75 --
    conventional defaults, not tuned against this corpus (too small a
    corpus, 30 documents, to meaningfully tune hyperparameters without
    overfitting to it)."""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.corpus_tokens = corpus_tokens
        self.doc_lens = [len(d) for d in corpus_tokens]
        self.n = len(corpus_tokens)
        self.avgdl = (sum(self.doc_lens) / self.n) if self.n else 0.0
        df: Counter = Counter()
        for doc in corpus_tokens:
            df.update(set(doc))
        self.idf = {term: math.log((self.n - freq + 0.5) / (freq + 0.5) + 1) for term, freq in df.items()}

    def scores_for_query(self, query_tokens: list[str]) -> list[float]:
        scores = []
        for i, doc in enumerate(self.corpus_tokens):
            freqs = Counter(doc)
            dl = self.doc_lens[i] or 1
            score = 0.0
            for term in query_tokens:
                if term not in freqs:
                    continue
                f = freqs[term]
                idf = self.idf.get(term, math.log(self.n + 1))
                score += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append(score)
        return scores


@lru_cache(maxsize=1)
def _bm25_index() -> BM25:
    return BM25([_tokenize(c.text) for c in load_chunks()])


@lru_cache(maxsize=1)
def _embedding_provider():
    from controlplane.models.local_hf_provider import LocalHFEmbeddingProvider

    return LocalHFEmbeddingProvider()


def _min_max_normalize(values: list[float]) -> list[float]:
    if not values:
        return values
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _ranks_descending(values: list[float]) -> list[int]:
    """1-indexed rank of each item if ``values`` were sorted descending
    (rank 1 = highest score). Ties broken by original index (stable) --
    fine for this corpus's scale, not claimed to be a tie-breaking
    policy that matters at larger scale."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    ranks = [0] * len(values)
    for rank, i in enumerate(order, start=1):
        ranks[i] = rank
    return ranks


def rrf_fusion(dense_scores: list[float], lexical_scores: list[float], k_constant: int = 60) -> list[float]:
    """Reciprocal Rank Fusion (Cormack, Clarke & Büttcher, 2009):
    ``score(d) = sum over each ranker of 1 / (k_constant + rank(d))``.
    ``k_constant=60`` is the paper's own reported default, not tuned
    against this corpus (same reasoning as BM25's untuned k1/b above --
    30 documents is too small to tune a rank-fusion constant without
    overfitting to it). Operates on RANKS, not raw scores, which is
    exactly why RRF needs no score normalization step (unlike the
    min-max weighted-sum alternative) -- dense cosine similarities and
    BM25 scores live on completely different, incomparable scales."""
    dense_ranks = _ranks_descending(dense_scores)
    lexical_ranks = _ranks_descending(lexical_scores)
    return [1.0 / (k_constant + dr) + 1.0 / (k_constant + lr) for dr, lr in zip(dense_ranks, lexical_ranks)]


@dataclass
class RetrievedChunk:
    chunk: Chunk
    dense_score: float
    lexical_score: float
    fused_score: float
    cross_encoder_score: float | None = None
    """Set only when ``retrieve(..., rerank=True)`` -- sigmoid-normalized
    cross-encoder relevance score, distinct from ``fused_score`` (see
    ``controlplane.rag.reranker``)."""


@lru_cache(maxsize=1)
def _reranker():
    from controlplane.rag.reranker import get_reranker

    return get_reranker()


def retrieve(
    query: str,
    k: int = 5,
    dense_weight: float = 0.5,
    rerank: bool = False,
    candidate_multiplier: int = 3,
    fusion_method: str = "rrf",
) -> list[RetrievedChunk]:
    """``rerank=True`` adds a second stage: widen candidate generation to
    ``max(k * candidate_multiplier, 10)`` chunks via fusion, then
    re-score/re-sort that candidate set with the real cross-encoder
    (``controlplane.rag.reranker``), truncating to ``k``. Default
    ``False`` keeps existing callers' behavior (fusion-ranked top-k)
    unchanged; ``RAGCapability`` opts in.

    ``fusion_method``: ``"rrf"`` (default, per the source-of-truth spec)
    or ``"min_max"`` (the pre-Milestone-8 weighted-sum method, kept for
    comparison/reproducibility -- ``dense_weight`` only applies to
    ``"min_max"``; RRF has no weighting parameter by design)."""
    if fusion_method not in ("rrf", "min_max"):
        raise ValueError(f"unknown fusion_method {fusion_method!r} -- expected 'rrf' or 'min_max'")

    chunks = load_chunks()
    if not chunks:
        return []

    query_embedding = np.array(_embedding_provider().embed(text=query).embedding, dtype=np.float32)
    dense_scores = [cosine_similarity(query_embedding, c.embedding) for c in chunks]
    lexical_scores = _bm25_index().scores_for_query(_tokenize(query))

    if fusion_method == "rrf":
        fused = rrf_fusion(dense_scores, lexical_scores)
    else:
        dense_norm = _min_max_normalize(dense_scores)
        lexical_norm = _min_max_normalize(lexical_scores)
        fused = [dense_weight * d + (1 - dense_weight) * l for d, l in zip(dense_norm, lexical_norm)]

    candidate_k = min(len(chunks), max(k * candidate_multiplier, 10)) if rerank else k
    order = sorted(range(len(chunks)), key=lambda i: fused[i], reverse=True)[:candidate_k]
    candidates = [
        RetrievedChunk(chunk=chunks[i], dense_score=dense_scores[i], lexical_score=lexical_scores[i], fused_score=fused[i])
        for i in order
    ]
    if not rerank:
        return candidates
    return _reranker().rerank(query, candidates, top_k=k)
