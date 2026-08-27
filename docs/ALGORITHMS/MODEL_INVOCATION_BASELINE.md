# Model Invocation Baseline

**Status:** IMPLEMENTED (Milestone 1, 2026-08-27)
**Version:** v0 (baseline -- no routing, no fine-tuning)

Implementation/architecture note, not a research algorithm document.

## 1. Problem

Given a user query, produce a model response and record everything needed to reconstruct what happened (which model, latency, tokens, success/failure) -- without any query intelligence, routing, or evaluation yet (those are later layers).

## 2. Architecture Location

`controlplane/runtime.py` (`Runtime._invoke_model`), backed by `controlplane/models/` (SS provider abstraction, `MODEL_PROVIDER_ABSTRACTION.md`) and persisted via `controlplane/db/models.py::ModelInvocationRecord`.

## 3. Inputs

The raw user query string, unmodified -- no prompt template, no system prompt, no few-shot examples. This is intentional: prompt engineering is out of scope until a real quality signal (Layer 13, Baseline Evaluation) exists to measure it against.

## 4. Outputs

The model's raw text response, returned to the caller as `ResponseEnvelope.answer`, plus telemetry (`model_invocations` row, `execution_ledger` MODEL_INVOKED entry, `MODEL_CALLED`/`MODEL_FAILURE`/`FINAL_RESPONSE_GENERATED` events).

## 5. Candidate Methods

Not applicable -- there is exactly one method (call the one configured provider once, synchronously, no retries). Retry policy, multi-model comparison, and routing are explicitly deferred (bootstrap Milestone 1 SS4: "Do not build model routing yet. Use ONE explicitly configured model.").

## 6. Relevant Research

None yet. `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md` documents the eventual model pool (Qwen3 ~1.3B / Qwen3 4B / Grok API) and judge (Prometheus 2) decisions; Milestone 1 uses Groq (a real, available API) as the first concrete provider to prove the runtime backbone, ahead of implementing that full pool -- this is a schedule choice, not a reversal of that decision.

## 7. Dataset Requirements

None -- no training happens here.

## 8. Model Requirements

One Groq-hosted chat-completion model, selected via `GROQ_MODEL`.

## 9. Training/Fine-Tuning Requirements

None.

## 10. Compute Requirements

None locally.

## 11. Evaluation Metrics

Not yet measured (Layer 13 doesn't exist yet). Currently recorded per-invocation: `latency_ms`, `input_tokens`, `output_tokens`, `status`.

## 12. Failure Modes

See `MODEL_PROVIDER_ABSTRACTION.md` SS12 -- this baseline inherits those failure modes unchanged; it adds no new ones.

## 13. Alternatives

Batching multiple candidate models per query (for later comparison/routing) was considered and rejected for this milestone -- it belongs to Layer 10 (Model Routing) and the counterfactual-routing dataset already described in `docs/DATA/CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md` SS15, not to the runtime backbone milestone.

## 14. Final Decision

One explicit provider/model call per query, no retries, no routing. Errors are surfaced as structured failures rather than silently retried or masked.

## 15. Version

v0 -- 2026-08-27.

## 16. Experimental Results

See `MODEL_PROVIDER_ABSTRACTION.md` SS16 for the live validation run this baseline was proven against.
