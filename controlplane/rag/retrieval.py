"""Dense + lexical retrieval, a V0 score-fusion "reranker", and (new this
milestone) a real cross-encoder reranking stage.

Baseline choice (per bootstrap SS17/SS50/SS51 -- "choose a small
practical baseline," "do not implement every paper"):

- Dense: cosine similarity over the local embedding model's vectors
  (same model as the Query Profiler's k-NN baseline).
- Lexical: BM25, implemented from scratch (~40 lines) rather than adding
  a dependency -- consistent with this codebase's existing
  dependency-free-metrics precedent (``controlplane/experiments/metrics.py``).
- Score fusion: min-max-normalized 0.5 dense + 0.5 lexical -- the
  candidate-generation stage. Previously mislabeled "reranking"; a real
  cross-encoder (``controlplane.rag.reranker``) now does that job when
  ``rerank=True``, per the decision to no longer defer it -- see
  docs/PROJECT_STATE/DECISIONS.md and docs/EVALUATION/RAG_RESULTS.md for
  the measured comparison (dense vs dense+lexical vs dense+lexical+cross-encoder).

``retrieve()`` defaults to ``rerank=False`` (unchanged fusion-only
behavior, e.g. for existing callers/tests); ``RAGCapability`` -- the path
actually used by the runtime -- passes ``rerank=True`` so the
cross-encoder is a real, live stage, not decorative unused code.
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
) -> list[RetrievedChunk]:
    """``rerank=True`` adds a second stage: widen candidate generation to
    ``max(k * candidate_multiplier, 10)`` chunks via fusion, then
    re-score/re-sort that candidate set with the real cross-encoder
    (``controlplane.rag.reranker``), truncating to ``k``. Default
    ``False`` keeps existing callers' behavior (fusion-ranked top-k)
    unchanged; ``RAGCapability`` opts in."""
    chunks = load_chunks()
    if not chunks:
        return []

    query_embedding = np.array(_embedding_provider().embed(text=query).embedding, dtype=np.float32)
    dense_scores = [cosine_similarity(query_embedding, c.embedding) for c in chunks]
    lexical_scores = _bm25_index().scores_for_query(_tokenize(query))

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
