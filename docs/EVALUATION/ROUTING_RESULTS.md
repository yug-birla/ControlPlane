# Capability Router + Model Router Results

**Run:** `controlplane/experiments/evaluate_capability_router.py` and `evaluate_model_router.py`, 2026-08-28. Dataset: `query_profiles_validation` v0.1 (28 examples, SYNTHETIC provenance). Raw output: `RESULTS/capability_router_2026-08-28.json`, `RESULTS/model_router_2026-08-28.json`.

## Capability Router

| Metric | Value |
|---|---|
| Capability-set micro-F1 (post-routing, vs. taxonomy-derived expected hints) | 0.441 |
| Capability-set macro-F1 | 0.280 |
| Restriction rate | 1/28 |
| Graph validation pass rate | 28/28 |
| Validation examples combining HIGH_RISK+/predicted risk with an AGENT capability hint | **0** |

The capability-set F1 is close to, not identical to, the Query Profiler's own `capability_hints` numbers (`docs/EVALUATION/QUERY_PROFILER_RESULTS.md`: micro 0.476/macro 0.355) — expected, since restriction only changes the set for 1/28 examples. All 28 examples produce a structurally valid `ExecutionGraph` (no cycles, no unknown dependencies).

**The one restriction event:** `QP-198` had `SQL` restricted at policy tier `CRITICAL_ACTION` — this is the same query flagged as a risk-classification false positive in `docs/EVALUATION/RISK_PROFILER_RESULTS.md` (a sensitivity-classification error, not an agentic-action case). **Coverage gap, stated plainly:** zero validation examples combine a HIGH_RISK+ severity (predicted or ground truth) with an `AGENT` capability hint — the specific safety path this milestone's regression requirement (bootstrap §63) cares about most (blocking an agentic action under high risk) is exercised by unit tests (`tests/test_capability_router.py::test_high_risk_policy_tier_restricts_agent_capability_out_of_the_route`, `tests/test_model_router.py::test_agentic_request_with_agent_restricted_abstains`), not by this dataset. This is a gap in the validation dataset's coverage, not evidence the code path is untested.

## Model Router

| Action | Count |
|---|---|
| USE_FAST_MODEL | 17 |
| USE_STRONG_MODEL | 9 |
| HUMAN_REVIEW | 2 |
| ABSTAIN | 0 |

| Model role | Count |
|---|---|
| FAST | 17 |
| STRONG | 11 (9 USE_STRONG_MODEL + 2 HUMAN_REVIEW's underlying draft model) |

**Safety invariant: PASS.** No example — under either our own predicted risk (post-fix) or the dataset's ground-truth `risk` label, checked independently — reaches `USE_FAST_MODEL` or verification-free execution at `HIGH_RISK`/`CRITICAL` severity. This is checked both ways specifically so the routing-logic safety claim does not depend on Risk Profiler accuracy, which is separately and honestly documented as imperfect (`docs/EVALUATION/RISK_PROFILER_RESULTS.md`).

**Cost/latency comparison vs. "always use the strongest model":** 17/28 (60.7%) of queries route to FAST instead of unconditionally using STRONG. This is reported as a *rate*, not a dollar/millisecond figure — `expected_cost_class`/`expected_latency_class` are ESTIMATES (see `docs/ALGORITHMS/MODEL_ROUTER.md`), and no `GROQ_API_KEY` was available this session to measure real cost/latency by role. **NOT MEASURED:** actual $ or ms saved.

`ABSTAIN` was never reached on this dataset (0/28) because no validation example combines `actionability=agentic` with an `AGENT` capability hint that policy then restricts — covered by `tests/test_model_router.py::test_agentic_request_with_agent_restricted_abstains` instead, and manually verified end-to-end (see `docs/PROJECT_STATE/PROGRESS.md`) on a synthetic query ("Please process the refund for customer 123 immediately, execute it now.").

## What Was NOT Measured

- Real Groq FAST-vs-STRONG quality/latency/cost comparison (no `GROQ_API_KEY` this session — same limitation as Milestones 1-2's Groq-dependent measurements).
- Route accuracy against a ground-truth "correct model" label — no such label exists in this dataset (the routing spec's suggested schema, `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md` §35, was never populated for this project's data).
