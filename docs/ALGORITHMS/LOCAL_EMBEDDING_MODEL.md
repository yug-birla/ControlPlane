# Local Embedding Model Selection

**Status:** IMPLEMENTED (Milestone 2, 2026-08-28)

## Problem

Milestone 2 needs one small, practical local model for query understanding (embedding-based k-NN classification) that also serves the next milestone's RAG work, without downloading a large foundation model or multiple models serving the same role (bootstrap SS3-4).

## Hardware Inspected Before Selecting Anything

Recorded 2026-08-28: Intel i7-13620H (10 cores / 16 threads), 15.7GB RAM, Intel UHD integrated graphics (no discrete GPU/VRAM), ~117GB free disk. **Conclusion: CPU-only inference; pick a small model (well under 500MB) with fast CPU performance; no quantization needed given the model's size and available RAM headroom.**

## Architecture Location

`controlplane/models/local_hf_provider.py` (`LocalHFEmbeddingProvider`), `controlplane/models/embedding_provider.py` (the `EmbeddingProvider` interface it implements), `controlplane/models/model_download.py` (setup-time download, never at request time).

## Candidate Alternatives Considered

| Model | Params | Why not selected |
|---|---|---|
| `sentence-transformers/all-mpnet-base-v2` | ~110M | ~3x larger, ~5x slower on CPU, for accuracy gains this milestone's baseline doesn't need yet |
| `BAAI/bge-small-en-v1.5` | ~33M | Reasonable alternative; not selected only because all-MiniLM-L6-v2 is smaller still and is the most widely-used, best-documented option in this size class |
| A local generation model (e.g. a small Llama/Qwen variant) | 1B+ | Not needed this milestone — Groq already covers generation (Milestone 1); bootstrap SS3 explicitly asks for an embedding model, not a second generation model |

**Selected: `sentence-transformers/all-MiniLM-L6-v2`**, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (pinned; verified live against the Hugging Face API on 2026-08-27/28, not recalled from training data).

## Model Details (Verified, Not Invented)

- **Repository:** `sentence-transformers/all-MiniLM-L6-v2`, license `apache-2.0` (confirmed via the live HF API).
- **Architecture:** BERT, 6 hidden layers, hidden_size=384, 12 attention heads, vocab 30522 (from the repo's own `config.json`).
- **Parameter count:** ~22.7M — corroborated by file-size arithmetic (`model.safetensors` = 90,868,376 bytes ÷ 4 bytes/fp32 param ≈ 22.7M), not just cited from memory.
- **Embedding dimension:** 384. **Max sequence length:** 256 tokens (`sentence_bert_config.json`).
- **Disk size:** ~90.9MB (the actual weight file; `snapshot_download` fetched the full repo including unused ONNX/OpenVINO/TF variants — ~5.6GB total on disk currently, a known inefficiency; a future re-download with `allow_patterns` restricted to the PyTorch/safetensors files would avoid this).

## Inputs / Outputs

Input: a text string (query or exemplar). Output: `EmbeddingResult` (384-dim float vector, latency_ms, device, provider/model identity) — see `controlplane/models/embedding_provider.py`.

## Dataset

None required for the embedding model itself (pretrained, no fine-tuning). Used as the encoder for the exemplar bank in `controlplane/query_intelligence/exemplar_bank.py` (135 train-split query profiles).

## Training / Fine-Tuning Requirement

None. Not fine-tuned (bootstrap SS21: no fine-tuning without a measured baseline gap first — none has been measured here).

## Compute

CPU-only, ~200MB RAM for the model itself.

## Latency (Measured, Not Estimated)

See `docs/EVALUATION/MODEL_BENCHMARKS.md`: cold start 20.1s (one-time, includes model load), warm p50=16ms, p95=32ms, p99=47ms, ~50 QPS single-threaded.

## Failure Modes

- Model not yet downloaded/cached -> `EmbeddingProviderError` raised cleanly (never a silent network fetch mid-request) -- see `tests/test_local_hf_provider.py::test_missing_local_model_fails_cleanly_instead_of_downloading`.
- `sentence-transformers` not installed -> same error class, clear message.

## Result

Live-verified offline load (network fully disabled via `HF_HUB_OFFLINE=1`) succeeds and produces correct 384-dim embeddings — see `tests/test_local_hf_provider.py`.

## Final Decision

Adopted as the sole local model for Milestone 2 (query understanding) and reserved for Milestone 3's RAG retrieval, avoiding a second embedding model download for that purpose (bootstrap SS27 explicitly permits downloading it now for that reason).

## Version

v1 -- 2026-08-28.
