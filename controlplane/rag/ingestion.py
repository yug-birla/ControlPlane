"""Document ingestion + chunking + embedding for the RAG corpus.

Corpus: ``data/synthetic_enterprise/documents/`` (30 files, 784 words
total -- verified by inspection, not assumed; these are short internal
policy statements, not long documents, so chunking mostly yields one
chunk per document with a couple of multi-sentence documents split into
two). Reuses the same local embedding model already selected in
Milestone 2 (``controlplane.models.local_hf_provider`` -- deliberately
chosen to double as the retrieval encoder, per
docs/PROJECT_STATE/DECISIONS.md, so no second model download).

Embeddings are disk-cached via ``controlplane.models.embedding_cache``
(the same B9 fix used for the Query Profiler's exemplar bank) so
retrieval results are reproducible across sessions regardless of
library version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from controlplane.models.embedding_cache import cached_embed_batch

_DOCS_DIR = Path(__file__).resolve().parents[2] / "data/synthetic_enterprise/documents"
_CACHE_PATH = Path(__file__).resolve().parents[2] / "data/cache/rag_chunk_embeddings.npz"

_MAX_CHUNK_WORDS = 60
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_name: str
    text: str
    embedding: np.ndarray


def _document_title(path: Path) -> str:
    return path.stem.replace("_", " ").title()


def _chunk_text(text: str) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        words = sentence.split()
        if current and current_len + len(words) > _MAX_CHUNK_WORDS:
            chunks.append(" ".join(current))
            current, current_len = [], 0
        current.append(sentence)
        current_len += len(words)
    if current:
        chunks.append(" ".join(current))
    return chunks or [text.strip()]


def _load_raw_chunks() -> list[tuple[str, str, str]]:
    """[(chunk_id, document_name, text)] in a stable, sorted order."""
    raw: list[tuple[str, str, str]] = []
    for path in sorted(_DOCS_DIR.glob("*.txt")):
        title = _document_title(path)
        text = path.read_text(encoding="utf-8-sig").strip()
        for i, chunk_text in enumerate(_chunk_text(text)):
            raw.append((f"{path.stem}#{i}", title, chunk_text))
    return raw


@lru_cache(maxsize=1)
def load_chunks() -> list[Chunk]:
    from controlplane.models.local_hf_provider import MODEL_REVISION, LocalHFEmbeddingProvider

    raw = _load_raw_chunks()
    texts = [text for _, _, text in raw]

    def _compute(texts: list[str]) -> np.ndarray:
        provider = LocalHFEmbeddingProvider()
        results = provider.embed_batch(texts=texts)
        return np.array([r.embedding for r in results], dtype=np.float32)

    embeddings = cached_embed_batch(_CACHE_PATH, MODEL_REVISION, texts, _compute)

    return [
        Chunk(chunk_id=chunk_id, document_name=doc_name, text=text, embedding=embedding)
        for (chunk_id, doc_name, text), embedding in zip(raw, embeddings)
    ]
