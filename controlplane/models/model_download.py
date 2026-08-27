"""Setup-time model download -- run this, never a request handler, to
populate the local Hugging Face cache. bootstrap SS14: "Do not download a
model during a user request."

Usage:
    .venv/Scripts/python -m controlplane.models.model_download
"""

from __future__ import annotations

import sys
import time

from controlplane.models.local_hf_provider import MODEL_REPO, MODEL_REVISION


def ensure_local_models_downloaded() -> dict:
    from huggingface_hub import snapshot_download

    start = time.monotonic()
    path = snapshot_download(repo_id=MODEL_REPO, revision=MODEL_REVISION)
    elapsed_s = time.monotonic() - start
    return {"repo": MODEL_REPO, "revision": MODEL_REVISION, "path": path, "elapsed_s": round(elapsed_s, 1)}


def main() -> int:
    print(f"Downloading {MODEL_REPO}@{MODEL_REVISION} (if not already cached)...")
    result = ensure_local_models_downloaded()
    print(f"OK: cached at {result['path']} ({result['elapsed_s']}s)")

    # Verify it now loads fully offline, proving no request-time download risk.
    import os

    os.environ["HF_HUB_OFFLINE"] = "1"
    from controlplane.models.local_hf_provider import LocalHFEmbeddingProvider

    provider = LocalHFEmbeddingProvider()
    probe = provider.embed(text="offline load verification")
    print(f"OK: offline load verified, embedding_dimension={probe.embedding_dimension}, latency_ms={probe.latency_ms}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
