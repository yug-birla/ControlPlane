"""Embedding k-NN prompt-injection detector -- built after a real,
measured failure: ``PromptInjectionEvaluator``'s fixed 18-phrase keyword
list scored 1.0 accuracy on this project's own 12 hand-authored cases,
then a 98.5% FALSE NEGATIVE RATE (recall=0.02) against the real, public
`deepset/prompt-injections` dataset (662 examples) -- exact-phrase
matching cannot generalize across the enormous paraphrase diversity of
real injection attempts ("forget all previous tasks" / "ignore all
preceding orders" / "now forget about all the previous information" all
mean the same thing but share almost no literal substring).

Per bootstrap SS9/SS10 ("do not depend primarily on fixed keywords for
semantic risk... move toward a small local model when the
representation is shown insufficient, retain deterministic hard
constraints, benchmark the improved approach"): this reuses the SAME
local embedding model already validated everywhere else in this project
(``all-MiniLM-L6-v2``) -- no new model download, no fine-tuning. It is a
frozen embedding function plus labeled reference data (majority-vote
k-NN), the same "no training step" pattern already established by
``controlplane.query_intelligence.knn_profiler``.

Reference set: the dataset's own TRAIN split (546 examples). Evaluated
only against the held-out TEST split (116 examples) -- using the TRAIN
examples as reference data is not leakage precisely because k-NN's
"model" IS that reference data (same reasoning already applied to the
Query Profiler's exemplar bank); reporting an accuracy number on
examples also used as neighbors would be.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from controlplane.models.embedding_cache import cached_embed_batch

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "injection_knn_embeddings.npz"
_REFERENCE_DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "external" / "deepset_prompt_injections" / "prompt_injections_normalized.json"
)


@dataclass(frozen=True)
class InjectionExample:
    text: str
    label: str  # "INJECTION_PATTERN_DETECTED" | "NO_PATTERN_DETECTED"
    embedding: np.ndarray


@dataclass
class InjectionKNNResult:
    label: str
    confidence: float
    """Fraction of the k nearest neighbors agreeing with ``label``."""
    nearest_examples: list[tuple[str, str, float]]
    """[(text, label, cosine_similarity), ...] for the k neighbors, for
    an auditable "why" -- never a black-box score alone."""


def _cosine_similarity_batch(query_embedding: np.ndarray, reference_embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(reference_embeddings, axis=1) * (np.linalg.norm(query_embedding) or 1e-9)
    norms = np.where(norms == 0, 1e-9, norms)
    return (reference_embeddings @ query_embedding) / norms


class EmbeddingKNNInjectionDetector:
    """``similarity_threshold`` (NEW -- found via a real end-to-end
    regression, not designed upfront): a real end-to-end test caught the
    original threshold-less version flagging a completely benign SQL
    query as an injection attempt, because plain k=5 majority-vote
    always returns *some* label even when every neighbor's cosine
    similarity is barely above 0.2 (near-orthogonal, not a meaningful
    semantic match). Below ``similarity_threshold`` the detector now
    abstains to the safe default (``NO_PATTERN_DETECTED``) regardless of
    the vote -- a k-NN "reject option."

    Default ``similarity_threshold=0.30`` is a deliberate choice, NOT the
    raw calibration-optimal value found by grid search on a held-out
    slice of TRAIN (0.20, calibration macro-F1 0.435 vs 0.419 at 0.30 --
    see ``controlplane/experiments/evaluate_injection_knn.py``). That
    calibration slice is drawn from the *same* dataset distribution as
    the reference set (deepset's casual-assistant-question collection
    style) -- it cannot reveal how a threshold behaves on ControlPlane's
    actual live traffic, which looks nothing like that (SQL/RAG/agent-
    tool queries). The exact false positive this guards against was
    real, not hypothetical: a benign SQL query's best-matching neighbor
    had cosine similarity 0.245 -- correctly rejected at 0.30, but would
    have been misclassified at the raw-optimal 0.20. 0.30 trades a small,
    measured amount of in-domain calibration performance for materially
    better protection against this project's actual out-of-domain query
    shapes -- a documented judgment call, not an arbitrary tweak."""

    name = "injection_knn_v0"

    def __init__(
        self, reference_examples: list[dict], k: int = 5, similarity_threshold: float = 0.30, cache_path: Path | None = None
    ) -> None:
        self._similarity_threshold = similarity_threshold
        from controlplane.models.local_hf_provider import MODEL_REVISION, LocalHFEmbeddingProvider

        self._k = k
        self._texts = [r["query"] for r in reference_examples]
        self._labels = [r["expected_label"] for r in reference_examples]

        def _compute(texts: list[str]) -> np.ndarray:
            provider = LocalHFEmbeddingProvider()
            results = provider.embed_batch(texts=texts)
            return np.array([res.embedding for res in results], dtype=np.float32)

        self._embeddings = cached_embed_batch(cache_path or _CACHE_PATH, MODEL_REVISION, self._texts, _compute)
        self._provider = LocalHFEmbeddingProvider()

    def classify(self, query: str) -> InjectionKNNResult:
        q_embedding = np.array(self._provider.embed(text=query).embedding, dtype=np.float32)
        sims = _cosine_similarity_batch(q_embedding, self._embeddings)
        top_k_idx = np.argsort(sims)[::-1][: self._k]
        nearest = [(self._texts[i], self._labels[i], float(sims[i])) for i in top_k_idx]

        if nearest[0][2] < self._similarity_threshold:
            # Reject option: nothing in the reference set is actually
            # close to this query -- a majority vote among barely-related
            # neighbors is noise, not signal. Default to the safe label.
            return InjectionKNNResult(label="NO_PATTERN_DETECTED", confidence=0.0, nearest_examples=nearest)

        neighbor_labels = [self._labels[i] for i in top_k_idx]
        vote = Counter(neighbor_labels)
        label, count = vote.most_common(1)[0]
        confidence = count / self._k
        return InjectionKNNResult(label=label, confidence=confidence, nearest_examples=nearest)


def _load_train_reference_examples() -> list[dict]:
    """Only the dataset's own TRAIN split (546 examples) -- the TEST
    split (116) must stay held out for evaluation
    (``controlplane/experiments/evaluate_injection_knn.py``), never used
    as k-NN reference data, or that evaluation would be measuring
    accuracy against examples the detector had effectively already
    "seen." Raises with a clear message if the dataset hasn't been
    fetched yet (never silently falls back to an empty/fake reference
    set)."""
    if not _REFERENCE_DATA_PATH.exists():
        raise FileNotFoundError(
            f"{_REFERENCE_DATA_PATH} does not exist -- run "
            "python -m data.external.deepset_prompt_injections.fetch_and_normalize first"
        )
    with open(_REFERENCE_DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)
    return [r for r in records if r["split"] == "train"]


@lru_cache(maxsize=1)
def get_injection_knn_detector() -> EmbeddingKNNInjectionDetector:
    """Process-wide singleton (same pattern as
    ``controlplane.rag.retrieval._embedding_provider``/``_reranker``,
    ``controlplane.judge.local_judge.get_local_judge``) -- builds the
    546-example reference embedding set once per process, not once per
    ``Runtime``/``PromptInjectionEvaluator`` instance. Disk-cached
    (``cached_embed_batch``) so even the first build in a fresh process
    is fast after the very first run ever."""
    return EmbeddingKNNInjectionDetector(_load_train_reference_examples(), k=5)
