# controlplane/models/

**Purpose:** the model provider abstraction. See `docs/ALGORITHMS/MODEL_PROVIDER_ABSTRACTION.md` for the full design rationale.

## Interface

- `provider.py`: `ModelProvider` (ABC), `ModelResult`, `ModelProviderError`/`ModelProviderTimeout`. Everything outside this package depends only on these.
- `groq_provider.py`: `GroqProvider(ModelProvider)` — the only module allowed to import the `groq` SDK.
- `registry.py`: `get_configured_provider(settings) -> ModelProvider` — resolves the one configured provider. Raises `ConfigurationError` if `GROQ_API_KEY`/`GROQ_MODEL` aren't set; never fabricates a default.

## Dependencies

The `groq` package (only inside `groq_provider.py`). `GROQ_API_KEY` read from the environment only — never logged, never given a fallback value, never persisted (see `docs/PROJECT_STATE/DECISIONS.md`).

## Limitations

Not a Model Capability Registry (that's Layer 10 — multiple registered models, capability profiles). Exactly one provider/model, no routing, no retries, no streaming.

## Extension points

Layer 10 (Model Routing) adds more `ModelProvider` implementations and a router that chooses between them at request time, behind this same interface.
