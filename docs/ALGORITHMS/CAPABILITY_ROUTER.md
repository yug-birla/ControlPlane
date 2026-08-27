# Capability Router

**Status:** IMPLEMENTED — V0 rules+taxonomy (Milestone 3, 2026-08-28)

## Problem

Answer "what capabilities does this query need, and in what dependency/parallel structure should they run?" (`docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` §10-15), then turn that into an `ExecutionGraph`.

## Architecture Location

`controlplane/routing/capability_router.py`. Consumed by `controlplane/runtime.py::_route`.

## Baseline: Rules + Taxonomy (V0)

Deliberately does **not** re-classify the query (spec §3: "ONE cheap query-intelligence inference ... should be sufficient"). Reuses `QueryFingerprint.capability_hints` — already produced and measured by the Query Profiler (`docs/EVALUATION/QUERY_PROFILER_RESULTS.md`) — and adds exactly two things a classifier alone can't: (1) policy filtering (`PolicyDecision.restricted_capabilities` removes e.g. `AGENT` at `HIGH_RISK`+ tiers) and (2) graph construction (data-fetch capabilities `SQL`/`RAG`/`WEB`/`CHAT_HISTORY`/`MEMORY` run in parallel, feed a `merge` node, then a `generation` node; `AGENT` — if not restricted — runs after `generation`).

## Candidate Alternatives

- **A second independent capability classifier** — rejected: would duplicate the Query Profiler's job and add a second inference call per request for no new signal (spec §3's explicit anti-pattern).
- **A fine-tuned multi-label classifier (spec V1/V2)** — deferred; no measured gap yet justifies it (bootstrap §21/§58).

## Inputs / Outputs

Input: `QueryFingerprint`, `RiskProfile`, `PolicyDecision`. Output: `CapabilityRoute` (selected capabilities, restricted-removed list, `ExecutionGraph`, human-readable reason, ESTIMATE cost/latency class).

## Dataset

`query_profiles_validation` (28 examples) — see `docs/EVALUATION/ROUTING_RESULTS.md`.

## Training / Fine-Tuning Requirement

None.

## Compute / Latency

Pure Python, no model call — negligible (<1ms), by design cheaper than the model it's deciding about (spec §3).

## Metrics

See `docs/EVALUATION/ROUTING_RESULTS.md`: capability-set F1 after routing (should ≈ the Query Profiler's own capability_hints numbers, since restriction almost never fires on this dataset), restriction rate, graph-validation pass rate (28/28).

## Failure Modes

An empty post-restriction capability set floors to `[GENERAL]` (never an unroutable empty request — same floor rule the Query Profiler already uses). `MULTI_SOURCE` is a signal, never itself scheduled as a graph node.

## Result

28/28 validation examples produce a structurally valid graph (no cycles, no unknown dependencies). The dataset does not contain an example combining ground-truth-or-predicted `HIGH_RISK`+ severity with an `AGENT` capability hint, so the restriction path is verified by targeted unit tests (`tests/test_capability_router.py`) rather than this dataset — a documented coverage gap, not an untested code path.

## Final Decision

V0 rules+taxonomy adopted as the runtime default. V1 (pretrained encoder + classifier heads) and V2 (fine-tuned) deferred per bootstrap §21.

## Version

v1 — 2026-08-28.
