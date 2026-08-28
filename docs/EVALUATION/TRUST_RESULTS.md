# Trust Layer Results

**Status:** Unit-tested only — no large-scale measurement performed this milestone.

## Why No Benchmark Table Here

`controlplane.trust.engine.TrustEngine` is a deterministic composition of already-validated signals (Verification status, Decision Engine action/attempt count, Risk severity) — see `docs/ALGORITHMS/TRUST_LAYER.md`. There is no independent ground truth for "was this response actually trustworthy" beyond the definitional composition rule itself, so there is nothing to calibrate accuracy against the way `RAG_RESULTS.md`/`AGENT_GOVERNANCE_RESULTS.md` calibrate against external labels. Reporting a fabricated "trust accuracy" number here would violate bootstrap SS65's "no false claims."

## What Was Verified

`tests/test_trust_engine.py` — 5 cases, one per branch of the composition (first-pass VERIFIED+low-risk → HIGH; REJECTED → LOW; VERIFIED+HIGH_RISK → capped MEDIUM; VERIFIED-after-retry → MEDIUM; NOT_VERIFIED → LOW), all passing. Also exercised end-to-end by every control-loop scenario test and the dashboard's `test_dashboard_detail_shows_a_derived_trust_level`.

## Known Limitations

- Only 3 of bootstrap SS36's suggested input signals are used (verification, decision, risk) — "evaluator agreement," "data quality," and "model reliability" are not incorporated (no such metrics exist yet to feed it).
- Not shown in the aggregate/historical dashboard view, only the per-request detail view.
