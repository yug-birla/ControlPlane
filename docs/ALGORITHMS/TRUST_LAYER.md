# Trust Layer

**Status:** IMPLEMENTED — V0 (Milestone 6, 2026-08-28)

## Problem

Bootstrap SS36: give every response a structured `HIGH`/`MEDIUM`/`LOW` trust verdict plus a stated reason and supporting evidence — explicitly never an invented arbitrary percentage/confidence number.

## Architecture Location

`controlplane/trust/engine.py`. Called from `Runtime.handle()` right after Verification; also recomputed (not re-stored) in `controlplane/dashboard/queries.py::get_request_detail` for the dashboard's Trust panel.

## Method

A pure, deterministic composition of three already-computed signals — no new score invented from scratch: `VerificationResult.status`, `ControlDecision.action`/`attempt_number`, and `RiskProfile.severity`. Order of checks: `REJECTED`→`LOW`; `NOT_VERIFIED`→`LOW`; risk `HIGH_RISK`/`CRITICAL`→capped at `MEDIUM` regardless of verification outcome; `PARTIALLY_VERIFIED`→`MEDIUM`; verified only after a retry (`attempt_number > 1`)→`MEDIUM`; otherwise (`VERIFIED`, first attempt, no elevated risk)→`HIGH`.

## Why Derived, Not Persisted

Trust is a pure function of data that is *already* persisted (`verifications`, `decisions`, `query_profiles.risk_vector`) — adding a new table to store a value that can always be recomputed identically from those rows would be redundant state, not new information. Recomputed fresh each time the dashboard detail view is loaded; a malformed/missing upstream field degrades to "not shown," never a fabricated level (see `queries.py`'s explicit `try/except` around reconstruction).

## Candidate Alternatives

- **A learned trust/confidence model** — rejected; no labeled "was this response actually trustworthy" dataset exists, and bootstrap SS36 explicitly warns against inventing a number without evidence backing it.
- **Persisting a `trust_assessments` table** — considered, rejected as redundant state (see above) given trust is cheap to recompute and never needs its own history distinct from the records it derives from.

## Inputs / Outputs

`engine.assess(verification, decision, risk) -> TrustAssessment` (`level`, `reason`, `contributing_factors`).

## Dataset

None — deterministic composition of already-validated signals, not a classifier requiring training/evaluation data of its own.

## Compute / Latency

Pure Python, no model call, no DB query beyond what Verification/Decision/Risk already required — negligible.

## Metrics

Unit-tested directly (`tests/test_trust_engine.py`, 5 cases covering every branch) and exercised indirectly by every dashboard/control-loop test that reaches a terminal decision. No separate large-scale "trust accuracy" measurement exists (there is no ground truth for what a response's trust level "should" be beyond the definitional composition rule itself) — see `docs/EVALUATION/TRUST_RESULTS.md`.

## Failure Modes

None observed; the composition is total (every `VerificationStatus` × `RiskSeverity` × attempt-count combination resolves to exactly one level).

## Known Limitations

- Only three input signals; bootstrap SS36 additionally lists "evaluator agreement," "data quality," and "model reliability" as candidate inputs — not incorporated this version (no evaluator-agreement metric or model-reliability score exists yet to feed it).
- Not shown in the request-list/aggregate dashboard view, only the per-request detail view (recomputing it for every listed row would need an additional batched decisions query not currently fetched at that granularity).

## Result

A real, structured, evidence-grounded (never arbitrary) trust verdict is computed for every request and shown with its reasoning in the dashboard.

## Final Decision

V0 composition adopted as the runtime default.

## Version

v1 — 2026-08-28.
