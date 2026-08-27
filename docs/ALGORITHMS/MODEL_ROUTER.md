# Model Router

**Status:** IMPLEMENTED — V0 threshold baseline (Milestone 3, 2026-08-28)

## Problem

Given the current query's risk/impact/complexity and the governing policy, decide `STATE -> ACTION` (`docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` §17: explicitly *not* a `query -> model` classifier).

## Architecture Location

`controlplane/routing/model_router.py`. Consumed by `controlplane/runtime.py::_route`; the resulting `model_role` ("FAST"/"STRONG") is resolved to an actual `ModelProvider` by `controlplane/models/registry.py::get_configured_provider(settings, role=...)`.

## Baseline: Threshold V0

```
actionability=agentic AND AGENT restricted by policy  -> ABSTAIN (no generation call)
policy tier in {HIGH_RISK, CRITICAL_ACTION}            -> HUMAN_REVIEW, role=STRONG, verification=True
impact in {HIGH, CRITICAL}                             -> USE_STRONG_MODEL, verification=True
complexity=HIGH                                        -> USE_STRONG_MODEL
complexity=LOW AND risk in {NO_ACTION, LOW_RISK}       -> USE_FAST_MODEL, verification=False
otherwise                                              -> USE_FAST_MODEL, verification=policy.required_verification
```

`ABSTAIN` exists for exactly one reason: generating an answer to an agentic request whose `AGENT` capability policy already blocked would risk misrepresenting that an action occurred when it did not. `HUMAN_REVIEW` still generates a draft (with the strongest model + mandatory verification) — it does not withhold an answer, since `AGENT`/`SQL` restriction (Capability Router) is the actual enforcement mechanism for consequential actions, not withholding the informational response.

## Candidate Alternatives

- **RouteLLM / a learned preference router (spec §40-41, V2+)** — deferred; no `model_comparisons.jsonl`-style pairwise preference data exists yet (bootstrap §21: no fine-tuning without a measured baseline gap).
- **Cascading (cheap-model-then-escalate-on-low-confidence)** — deferred to P1 (spec §29-32): would need a working confidence signal from an actual model response first.
- **A local generative model pool (Qwen3 ~1.3B/4B, `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md`)** as the FAST role — deferred; see `docs/PROJECT_STATE/DECISIONS.md` for why running a real local generative model (distinct from the embedding model already in use) was scoped out of this milestone. FAST and STRONG both currently resolve to Groq, distinguished only by `GROQ_MODEL_FAST`/`GROQ_MODEL_STRONG`.

## Inputs / Outputs

Input: `QueryFingerprint`, `RiskProfile`, `PolicyDecision`. Output: `ModelRouteDecision` (action, model_role, require_verification, human_approval_required, reason, ESTIMATE cost/latency class).

## Dataset

`query_profiles_validation` (28 examples) — see `docs/EVALUATION/ROUTING_RESULTS.md`. No ground-truth "correct model" label exists in this dataset (unlike the spec's suggested schema), so this is a distribution + safety-invariant evaluation, not an accuracy evaluation.

## Training / Fine-Tuning Requirement

None.

## Compute / Latency

Pure Python, no model call — negligible.

## Metrics

See `docs/EVALUATION/ROUTING_RESULTS.md`: action/role distribution (17/28 FAST, 9/28 STRONG, 2/28 HUMAN_REVIEW), a hard safety invariant (no example reaches `USE_FAST_MODEL`/unverified execution at `HIGH_RISK`+ severity, checked against both our own predicted risk and the dataset's ground-truth risk label).

## Failure Modes

If the Risk Profiler under-classifies severity (documented gap, `docs/EVALUATION/RISK_PROFILER_RESULTS.md`), the Model Router's own thresholds provide a second, independent line of defense via `fingerprint.impact`/`complexity` — but cannot fully compensate for a profiler that reports low risk *and* low impact/complexity for a genuinely risky query. This is why the risk classification gap was fixed at the source (see `docs/PROJECT_STATE/DECISIONS.md`) rather than papered over here.

## Result

Safety invariant **PASSES** on the full validation split, including the one true `HIGH_RISK` example (`QP-190`), using both predicted and ground-truth risk. 17/28 (60.7%) of queries route to FAST instead of unconditionally using STRONG — an estimated cost/latency reduction (ESTIMATE cost classes only; no live Groq benchmark this session).

## Final Decision

Threshold V0 adopted as the runtime default.

## Version

v1 — 2026-08-28.
