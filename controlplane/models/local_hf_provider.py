"""Local Hugging Face embedding provider.

Model: sentence-transformers/all-MiniLM-L6-v2, revision
1110a243fdf4706b3f48f1d95db1a4f5529b4d41 (pinned; verified via the live
Hugging Face API on 2026-08-27 -- see docs/ALGORITHMS/LOCAL_EMBEDDING_MODEL.md
for the full selection rationale and hardware fit).

Offline-first (bootstrap SS14): ``local_files_only=True`` is passed to the
underlying loader, so this class raises cleanly if the model isn't
already cached rather than silently downloading during a request. Use
``controlplane.models.model_download.ensure_local_models_downloaded()``
during setup/preparation to populate the cache -- never inside a request
path.

``sentence_transformers``/``torch`` are imported lazily (inside
``__init__``) so the rest of the codebase can be imported/tested even
before/without these (comparatively large) packages being installed.
"""

from __future__ import annotations

import time

from controlplane.models.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResult,
)

MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
EMBEDDING_DIMENSION = 384


class LocalHFEmbeddingProvider(EmbeddingProvider):
    name = "local_hf"

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderError(
                "sentence-transformers is not installed; run pip install -e \".[dev]\""
            ) from exc

        try:
            self._model = SentenceTransformer(
                MODEL_REPO, revision=MODEL_REVISION, local_files_only=True
            )
        except Exception as exc:
            raise EmbeddingProviderError(
                f"local model {MODEL_REPO}@{MODEL_REVISION} is not cached locally -- "
                "run controlplane.models.model_download.ensure_local_models_downloaded() "
                "during setup, never during a request"
            ) from exc
        self._device = str(self._model.device)

    def embed(self, *, text: str) -> EmbeddingResult:
        return self.embed_batch(texts=[text])[0]

    def embed_batch(self, *, texts: list[str]) -> list[EmbeddingResult]:
        start = time.monotonic()
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        latency_ms = int((time.monotonic() - start) * 1000)
        per_item_ms = max(1, latency_ms // max(1, len(texts)))
        return [
            EmbeddingResult(
                provider=self.name,
                model=MODEL_REPO,
                embedding=vec.tolist(),
                embedding_dimension=len(vec),
                latency_ms=per_item_ms,
                device=self._device,
                raw_metadata={"revision": MODEL_REVISION},
            )
            for vec in vectors
        ]
