# Model Provider Abstraction

**Status:** IMPLEMENTED (Milestone 1, 2026-08-27)
**Version:** v1

This is an implementation/architecture note, not a research algorithm document — there is no learned component here, just an interface decision.

## 1. Problem

ControlPlane needs to call LLM providers without the rest of the system (runtime, trajectory, ledger, events, future routing/evaluation) depending on any specific vendor SDK. Model routing (choosing between multiple providers/models) is a later layer (Layer 10); this milestone needs exactly one provider to work correctly, safely, and observably.

## 2. Architecture Location

`controlplane/models/`. `provider.py` defines the abstraction; `groq_provider.py` is the only module allowed to import the `groq` SDK; `registry.py` resolves the one configured provider from settings. `controlplane/runtime.py` depends only on `ModelProvider`/`ModelResult`.

## 3. Inputs

`ModelProvider.generate(*, prompt: str) -> ModelResult`. A single-turn prompt string. (No conversation history, system prompt, or tool-calling support yet — not needed until later layers.)

## 4. Outputs

`ModelResult`: `provider`, `model`, `content`, `input_tokens`, `output_tokens`, `latency_ms`, `finish_reason`, `raw_metadata` (safe/structured only — see SS9). No hidden reasoning/chain-of-thought field, even if a future provider's response includes one.

## 5. Candidate Methods

- **Hand-rolled HTTP client** against Groq's OpenAI-compatible REST endpoint. Rejected: reimplements auth/retry/error-shape handling the official SDK already does correctly.
- **Official `groq` Python SDK**, wrapped entirely inside `groq_provider.py`. **Adopted.**

## 6. Relevant Research

None — this is a systems/interface decision, not an ML method.

## 7. Dataset Requirements

None for the abstraction itself.

## 8. Model Requirements

Exactly one Groq-hosted chat-completion model, configured via `GROQ_MODEL` (never hard-coded — see SS9).

## 9. Training/Fine-Tuning Requirements

None. No fine-tuning at this milestone (per the bootstrap's fine-tuning policy).

## 10. Compute Requirements

None locally — inference happens on Groq's infrastructure.

## 11. Evaluation Metrics

Not applicable to the abstraction layer itself. Per-invocation `latency_ms`, `input_tokens`, `output_tokens` are recorded (`model_invocations` table, `docs/DATA/POSTGRES_SCHEMA.md` SS10.2) for future use by Layer 10 (Model Routing) and Layer 13 (Baseline Evaluation).

## 12. Failure Modes

- Missing/invalid `GROQ_API_KEY` or `GROQ_MODEL` -> `ConfigurationError` (never fabricated, never a silent fallback).
- Provider timeout -> `ModelProviderTimeout` -> mapped to `controlplane.errors.TimeoutError` (HTTP 504).
- Any other Groq API error (auth, rate limit, bad request, 5xx) -> `ModelProviderError` -> mapped to `controlplane.errors.DependencyError` (HTTP 502).
- All three failure modes are recorded in `model_invocations` (status=`FAILURE`, `error_metadata`), `execution_ledger` (MODEL_INVOKED, status=FAILURE), and emit a `MODEL_FAILURE` event, before the structured error is returned to the caller.

## 13. Alternatives

A generic `LiteLLM`-style multi-provider shim was considered and rejected for this milestone: it would anticipate Layer 10 (Model Routing) before it exists, adding complexity ("no premature intelligence" / "no unnecessary abstractions") the current single-provider requirement doesn't need. `ModelProvider` is deliberately a thin `ABC` so a router can be introduced later without changing this interface.

## 14. Decision

Adopted: `ModelProvider` ABC + `GroqProvider` adapter + `get_configured_provider(settings)` registry function returning exactly one provider instance. See `docs/PROJECT_STATE/DECISIONS.md`.

## 15. Version

v1 — 2026-08-27, Milestone 1.

## 16. Results

Live-validated against the real Groq API on 2026-08-27 (see `tests/manual_groq_live_check.py` and `docs/PROJECT_STATE/PROGRESS.md`): model `allam-2-7b` (chosen from Groq's live `/models` list, not hard-coded), latency 405-625ms, token usage recorded correctly, response content normalized correctly, no secrets or chain-of-thought persisted.
