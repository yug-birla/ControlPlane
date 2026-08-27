# controlplane/models/

**Purpose:** the model provider abstractions — remote generation (Groq) and local embedding (Hugging Face). See `docs/ALGORITHMS/MODEL_PROVIDER_ABSTRACTION.md` and `docs/ALGORITHMS/LOCAL_EMBEDDING_MODEL.md`.

## Interface

- `provider.py`: `ModelProvider` (ABC), `ModelResult`, `ModelProviderError`/`ModelProviderTimeout` — the **generation** interface. Everything outside this package depends only on these, never a specific SDK.
- `groq_provider.py`: `GroqProvider(ModelProvider)` — the only module allowed to import the `groq` SDK.
- `registry.py`: `get_configured_provider(settings, role="STRONG") -> ModelProvider` — resolves the Groq provider for the Model Router's `role` ("FAST"/"STRONG"; see `controlplane/routing/model_router.py`). `resolve_model_name(settings, role)` picks `GROQ_MODEL_FAST`/`GROQ_MODEL_STRONG`, falling back to `GROQ_MODEL` when the role-specific var is unset. Raises `ConfigurationError` if `GROQ_API_KEY` or the resolved model name aren't set; never fabricates a default.
- `embedding_provider.py`: `EmbeddingProvider` (ABC), `EmbeddingResult` — a **separate** interface from `ModelProvider` (an embedding call returns a vector, not generated text; see `docs/PROJECT_STATE/DECISIONS.md` for why these aren't forced into one hierarchy).
- `local_hf_provider.py`: `LocalHFEmbeddingProvider(EmbeddingProvider)` — the only module allowed to import `sentence_transformers`/`torch`. Offline-first (`local_files_only=True`); raises `EmbeddingProviderError` cleanly if the model isn't cached, never downloads mid-request.
- `model_download.py`: setup-time download (`python -m controlplane.models.model_download`) — never called from a request path.
- `registry_seed.py`: seeds `model_registry` with the local + remote model metadata (idempotent upsert).

## Dependencies

`groq` (only in `groq_provider.py`). `sentence-transformers`/`torch` (only in `local_hf_provider.py`/`model_download.py`). `GROQ_API_KEY` read from the environment only — never logged, never given a fallback value, never persisted.

## Limitations

Generation: one provider (Groq) behind two roles (FAST/STRONG), no retries, no streaming, no local generative model yet (see `docs/PROJECT_STATE/DECISIONS.md` on the deferred Qwen3 local tier) — full multi-provider Model Routing (Layer 10) is still future work. Embedding: one fixed local model, no batching optimization beyond `embed_batch`'s single forward pass.

## Extension points

Layer 10 (Model Routing across multiple *providers*, not just roles on one provider) adds more `ModelProvider` implementations (including a local generation model, if one is ever selected) behind `get_configured_provider`'s same signature — `controlplane/routing/model_router.py` would not need to change.
