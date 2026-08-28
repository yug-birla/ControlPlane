"""Exemplar bank for the embedding k-NN baseline.

Loads only the **train** split (`data/evaluation/train/query_profiles_train.json`,
135 records) as reference exemplars -- validation/test/challenge stay held
out for `docs/EVALUATION/`, never used as exemplars (basic ML hygiene:
using held-out data as training/reference data would make the evaluation
meaningless).

Labels in this dataset carry ``provenance: SYNTHETIC`` (LLM-generated
during the 2026-08-26 data-generation pass, not human-labeled -- see
docs/DATA/DATASET_GAPS.md). Every prediction is being measured against
another model's synthetic judgment, not human ground truth. This is
stated wherever these numbers are reported, per bootstrap SS17: "Never
treat LLM-generated labels as automatically equivalent to human ground
truth."
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from controlplane.models.embedding_cache import cached_embed_batch

_TRAIN_PATH = Path(__file__).resolve().parents[2] / "data/evaluation/train/query_profiles_train.json"
_CACHE_PATH = Path(__file__).resolve().parents[2] / "data/cache/exemplar_embeddings.npz"
"""Committed to the repository -- see docs/PROJECT_STATE/BLOCKERS.md B9.
Deleting this file is safe (it will be recomputed), but then this
process's embeddings depend on whatever sentence-transformers/torch
version is currently installed, reintroducing B9's cross-session drift
until the file is regenerated and re-committed."""

DATASET_ID = "query_profiles_train"
DATASET_VERSION = "v0.1"  # docs/DATA/DATA_CHANGELOG.md schema v0.1 freeze
ANNOTATION_SOURCE = "SYNTHETIC"


@dataclass(frozen=True)
class Exemplar:
    query_id: str
    query: str
    domain: str
    complexity: str
    sensitivity: str
    ambiguity: str
    actionability: str
    taxonomy_labels: tuple[str, ...]
    required_data_sources: tuple[str, ...]
    embedding: np.ndarray


def _load_records() -> list[dict]:
    with open(_TRAIN_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_exemplars() -> list[Exemplar]:
    """Cached in-process (``lru_cache``) *and* on disk (``_CACHE_PATH``,
    see ``embedding_cache.py`` / BLOCKERS.md B9) -- embeddings are
    computed once, ever, per (model revision, exact query text) and then
    reused byte-for-byte regardless of which library version a later
    session has installed."""
    from controlplane.models.local_hf_provider import MODEL_REVISION, LocalHFEmbeddingProvider

    records = _load_records()
    texts = [r["query"] for r in records]

    def _compute(texts: list[str]) -> np.ndarray:
        provider = LocalHFEmbeddingProvider()
        results = provider.embed_batch(texts=texts)
        return np.array([r.embedding for r in results], dtype=np.float32)

    embeddings = cached_embed_batch(_CACHE_PATH, MODEL_REVISION, texts, _compute)

    exemplars = []
    for record, embedding in zip(records, embeddings):
        exemplars.append(
            Exemplar(
                query_id=record["query_id"],
                query=record["query"],
                domain=record["domain"],
                complexity=record["complexity"],
                sensitivity=record["sensitivity"],
                ambiguity=record["ambiguity"],
                actionability=record["actionability"],
                taxonomy_labels=tuple(record["taxonomy_labels"]),
                required_data_sources=tuple(record["required_data_sources"]),
                embedding=embedding,
            )
        )
    return exemplars


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
    return float(np.dot(a, b) / denom)


def nearest(query_embedding: np.ndarray, k: int = 5) -> list[tuple[Exemplar, float]]:
    exemplars = load_exemplars()
    scored = [(ex, cosine_similarity(query_embedding, ex.embedding)) for ex in exemplars]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]
