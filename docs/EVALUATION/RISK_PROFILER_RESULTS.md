# Risk Profiler Results

**Run (Milestone 2):** `controlplane/experiments/evaluate_risk_profiler.py`, 2026-08-28 — see "Milestone 3 Fix" below; the Milestone 2 numbers in this section are retained for the historical record but are superseded by the Milestone 3 re-measurement. Dataset: `query_profiles_validation` v0.1 (28 examples, SYNTHETIC provenance).

## Headline Numbers (Milestone 2, before the fix)

| Metric | Value |
|---|---|
| Overall severity accuracy | 0.607 |
| Overall severity macro-F1 | 0.327 |
| True HIGH_RISK/CRITICAL examples in validation split | 1 |
| Missed (false negative on HIGH_RISK/CRITICAL) | **1 (100% miss rate on this split)** |
| False positives (flagged HIGH_RISK/CRITICAL, wasn't) | 1 |

## High-Risk Miss — Read This Before Trusting This Baseline for Anything Safety-Critical

Per bootstrap SS19 ("prioritize false-negative analysis" for high-risk categories, "do not claim the risk system is safe merely because aggregate accuracy is high"): the validation split contains exactly one ground-truth `HIGH_RISK` example, and the Milestone 2 baseline **missed it**:

> `QP-190`: "Given our recent SOC 2 audit findings regarding access governance, recommend whether we should implement an automated Identity Governance and Administration (IGA) tool or enhance internal review scripts." — labeled `HIGH_RISK`, `actionability=decisional`, `sensitivity=NONE`.

**Why it was missed:** none of the baseline's keyword lists (`_SECURITY_KEYWORDS`, `_FINANCIAL_KEYWORDS`, etc. in `controlplane/risk/baseline.py`) contain governance/compliance terminology ("access governance", "Identity Governance and Administration", "SOC 2"). The baseline's action-risk escalation only triggers for `actionability=agentic`; this example is `decisional` — a consequential *recommendation*, not an autonomous action — which the design did not treat as risk-elevating on its own.

## Milestone 3 Fix (2026-08-28)

Per this milestone's mandatory regression requirement (bootstrap §63) and Milestone 2's own recommendation above, `controlplane/risk/baseline.py` now adds a narrowly-scoped trigger: a governance/compliance keyword (`governance`, `compliance`, `audit`, `soc 2`, `iso 27001`, `regulatory`, `regulator`, `risk posture`) combined with a decision-oriented `intent` (`REASONING`, `RECOMMENDATION`, `DECISION_SUPPORT`, or `ANALYTICAL`) elevates the `action` dimension to `HIGH_RISK`. It is gated on `intent`, not `actionability=decisional` as originally recommended — verified empirically that `HybridQueryProfiler` predicts `actionability=informational` for QP-190 (the k-NN vote disagrees with the dataset's own label, another instance of the actionability weakness already documented in `docs/EVALUATION/QUERY_PROFILER_RESULTS.md`), while `intent=REASONING` is reliably set by a deterministic rule ("recommend" is a `_REASONING_KEYWORDS` hit) regardless of the k-NN path. Verified only QP-190 among the 28 validation examples contains any of the governance keywords, so this is a targeted fix, not a broad new trigger — confirmed by a second regression test (`test_governance_trigger_does_not_fire_without_a_decision_oriented_intent`) that a bare mention of "compliance" in a purely factual query does not elevate severity.

**Controlled A/B re-measurement, same session/environment, same dataset, only `controlplane/risk/baseline.py` toggled:**

| Metric | Before fix (Milestone 2 code, re-run today) | After fix (Milestone 3) |
|---|---|---|
| Overall severity accuracy | 0.500 | 0.536 |
| Overall severity macro-F1 | 0.266 | 0.521 |
| HIGH_RISK/CRITICAL missed | 1/1 (100%) | **0/1 (0%)** |
| False positives (flagged HIGH_RISK/CRITICAL, wasn't) | 1 | 1 (same example, QP-198 — see below; unrelated to this fix) |

QP-190 now classifies as exactly `HIGH_RISK` (matching ground truth), verified permanently by `tests/test_risk_profiler.py::test_qp190_governance_decision_support_regression` and, at the routing level, by `tests/test_model_router.py::test_qp190_style_high_risk_governance_case_never_reaches_fast_model_unverified`. End-to-end: this query now produces `model_route.action=HUMAN_REVIEW`, `model_role=STRONG`, `require_verification=True`, `human_approval_required=True` — a draft answer is still generated (Graceful Degradation, bootstrap §33), but flagged for mandatory human sign-off, matching the product behavior already observed for other HIGH_RISK cases in Milestone 2 (e.g. the refund example).

**This is a real, documented fix to a real gap, not a metric massaged after the fact:** the before/after numbers above are from the same code re-run in the same session specifically to isolate the effect of this one change from unrelated environment drift (see the reproducibility note below, which affects the *absolute* numbers but not this A/B comparison, since both sides of it ran in the identical environment).

## New False Positive Discovered This Milestone: QP-198

While building the Milestone 3 Capability Router evaluation, `QP-198` ("Can you update the risk assessment table we built three messages ago by adding a column for estimated financial impact?" — ground truth `risk=NO_ACTION`) was found to be classified `CRITICAL` by the baseline, both before and after the Milestone 3 fix (confirmed unrelated to it). Root cause: `HybridQueryProfiler` predicts `sensitivity=SENSITIVE_DATA_EXPOSURE` for this query (the k-NN vote is wrong — ground truth `sensitivity=NONE`), which maps directly to `RiskSeverity.CRITICAL` via `_SENSITIVITY_TO_SEVERITY`. This is a manifestation of the sensitivity-classification weakness already noted in `docs/EVALUATION/QUERY_PROFILER_RESULTS.md` ("hybrid loses to rules on sensitivity"), not a new independent bug. **This is a false positive (over-restriction), not a false negative** — Capability Router's policy filtering correctly restricted `SQL` for this request as a result, which is a safe failure direction (an unnecessary restriction, not a missed unsafe action), unlike the QP-190 miss above. Left as a documented limitation (DEFER — see `docs/PROJECT_STATE/BLOCKERS.md`), not patched reactively without broader evidence of the sensitivity classifier's failure pattern.

## Reproducibility Note (found during Milestone 3)

The *absolute* headline numbers above depend on `HybridQueryProfiler`'s embedding k-NN component, which was found this milestone to not reproduce exactly across sessions in this environment (same finding as `docs/EVALUATION/QUERY_PROFILER_RESULTS.md` — see that document for the investigation and hypothesis). The A/B comparison in "Milestone 3 Fix" above is unaffected by this, since both sides ran in the same process/session back-to-back.

## Per-Dimension Behavior (Not Accuracy-Scored — No Ground Truth Exists)

The dataset carries only one aggregate `risk` label per example; there is no ground truth for the 9 individual dimensions (factuality, reasoning, privacy, pii, security, bias, financial, action, safety), so only the combined `severity` is accuracy-scored above. Per-dimension trigger examples observed during this run are in `RESULTS/risk_profiler_2026-08-28.json` (`per_dimension_trigger_examples`) for qualitative inspection.

## Known Limitations

- **1 HIGH_RISK example in a 28-row validation split** makes the miss-rate statistically uninformative on its own (95% CI on 1/1 spans nearly the whole range) — now caught (0/1 missed after the fix), but a sample of 1 cannot establish a reliable miss *rate* going forward; new HIGH_RISK examples should be added to the validation set before trusting this number further.
- **No per-dimension ground truth** — the 9-dimension breakdown is unvalidated against anything.
- **Overall accuracy (53.6% post-fix) is on 5 severity classes** — a random baseline would score ~20%, so this is real signal, but well short of anything that should gate an actual HIGH_RISK/CRITICAL action without a human in the loop (which the Policy baseline already enforces independently — see `controlplane/policy/baseline.py` — so this limitation is mitigated by policy, not by profiler accuracy alone). Accuracy alone is also a misleading headline metric here: it dropped slightly post-fix (0.607→0.536 across environments, or 0.500→0.536 in the same-session A/B) while macro-F1 improved substantially (0.266→0.521 same-session) and the safety-critical miss went to zero — macro-F1 and the high-risk miss rate matter more for this component than raw accuracy.
- **QP-198 false positive (see above)** is a known, deferred, sensitivity-classification-driven over-restriction.
