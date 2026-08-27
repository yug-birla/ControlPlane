# controlplane/routing/

**Purpose:** Capability Router + Model Router — `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md`. See `docs/ALGORITHMS/CAPABILITY_ROUTER.md` and `docs/ALGORITHMS/MODEL_ROUTER.md`, and `docs/EVALUATION/ROUTING_RESULTS.md` for measured behavior.

## Interface

- `capability_router.py`: `CapabilityRouter.route(fingerprint, risk, policy) -> CapabilityRoute`. Filters `QueryFingerprint.capability_hints` through `PolicyDecision.restricted_capabilities`, then builds an `ExecutionGraph` (data-fetch capabilities in parallel → merge → generation → optional agent action).
- `model_router.py`: `ModelRouter.decide(fingerprint, risk, policy) -> ModelRouteDecision`. A `STATE -> ACTION` threshold baseline (spec §17), not a query→model classifier. Actions: `USE_FAST_MODEL`, `USE_STRONG_MODEL`, `HUMAN_REVIEW`, `ABSTAIN`.

Both are pure functions of already-computed inputs — no model call, no DB access (persistence happens in `controlplane/runtime.py::_route`, not here).

## Dependencies

`controlplane.execution.graph`, `controlplane.query_intelligence.fingerprint`, `controlplane.risk.profile`, `controlplane.policy.baseline`.

## Limitations

- Model Router only distinguishes FAST vs. STRONG (both resolved to Groq via `controlplane.models.registry`) — no local generative model pool yet (the Qwen3 tier from `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md` was deferred, see `docs/PROJECT_STATE/DECISIONS.md`). No cascading, no confidence-aware adaptive compute (spec §29-33, P1+).
- `expected_cost_class`/`expected_latency_class` on both routers are **ESTIMATES**, not measurements — no `GROQ_API_KEY` was available this session to benchmark real Groq cost/latency by role.
- Capability Router's restriction path (policy blocking `AGENT`/`SQL` at high risk tiers) is exercised by unit tests (`tests/test_capability_router.py`, `tests/test_model_router.py`) but essentially not by the validation dataset — see `docs/EVALUATION/ROUTING_RESULTS.md`'s coverage-gap finding.

## Extension points

A multi-provider Model Router (Layer 10's full scope) or a learned capability classifier both slot in behind the same `.route(...)`/`.decide(...)` signatures.
