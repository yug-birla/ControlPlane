"""Disk-cached embedding computation -- the concrete fix for
docs/PROJECT_STATE/BLOCKERS.md B9 (embedding k-NN results did not
reproduce exactly across sessions, traced to a probable ML-library
version difference between sessions, not code or per-run randomness).

Caches computed embeddings keyed by (embedding model revision, the exact
input texts) so a given code+data version always encodes to the same
vectors, regardless of which torch/sentence-transformers version happens
to be installed when the cache file is read. Cache files are committed
to the repository like any other reference dataset -- see
``controlplane/query_intelligence/exemplar_bank.py`` and
``controlplane/rag/ingestion.py`` for the two current callers -- so
every environment reproduces identical downstream k-NN/retrieval
results without needing matching library versions installed.

The cache key deliberately excludes the installed library version: once
computed and committed, the vectors are a frozen artifact, not something
that should silently change on a `pip install --upgrade`. If the
embedding model itself changes (a new revision) or the input texts
change, the key changes and the cache is transparently recomputed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

import numpy as np


def _cache_key(model_revision: str, texts: list[str]) -> str:
    h = hashlib.sha256()
    h.update(model_revision.encode("utf-8"))
    for t in texts:
        h.update(b"\x00")
        h.update(t.encode("utf-8"))
    return h.hexdigest()


def cached_embed_batch(
    cache_path: Path,
    model_revision: str,
    texts: list[str],
    compute_fn: Callable[[list[str]], np.ndarray],
) -> np.ndarray:
    """Returns a ``(len(texts), dim)`` float32 array. Recomputes (via
    ``compute_fn``) and rewrites the cache file only when the model
    revision or any input text changed since the file was written."""
    key = _cache_key(model_revision, texts)
    key_path = cache_path.with_suffix(".key")

    if cache_path.exists() and key_path.exists() and key_path.read_text(encoding="utf-8").strip() == key:
        with np.load(cache_path) as data:
            return data["embeddings"]

    embeddings = np.asarray(compute_fn(texts), dtype=np.float32)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache_path, embeddings=embeddings)
    key_path.write_text(key, encoding="utf-8")
    return embeddings
