# Risk Profiler Baseline

**Status:** IMPLEMENTED (Milestone 2, 2026-08-28)

## Problem

Assess risk across 9 dimensions (factuality, reasoning, privacy, pii, security, bias, financial, action, safety) from the Query Fingerprint + query text, without a learned risk model (bootstrap SS9 explicitly forbids one at this milestone).

## Architecture Location

`controlplane/risk/` — `profile.py` (schema, `RiskSeverity` enum reusing the already-canonical 5-value scale from `docs/DATA/ANNOTATION_GUIDELINES.md`), `baseline.py` (`BaselineRiskProfiler`). `controlplane/policy/baseline.py` (`PolicyBaseline`) maps the resulting severity to control requirements.

## Baseline Method

Rules + fingerprint, no learned model:
- **privacy/pii**: directly from the fingerprint's `sensitivity` field (already detected upstream).
- **action**: from `impact` + `actionability` (agentic actionability escalates).
- **factuality**: ungrounded generative/analytical intent with no `data_requirement` escalates.
- **reasoning**: high complexity escalates.
- **financial/security/bias/safety**: keyword-triggered.
- **severity** = max across all 9 dimensions, never a single opaque blended number (bootstrap SS9).
- **recommended_control_depth**: `DEEP_PATH` if severity is HIGH_RISK/CRITICAL or complexity is high, else `FAST_PATH` (reuses the existing Fast Path/Deep Path vocabulary from `docs/architecture/RUNTIME_FLOW.md`, not a new one).

Confidence is only ever reported for a dimension when a specific rule fired — never fabricated for a default "no signal" result (absence of a detected trigger is not evidence of safety).

## Candidate Alternatives

A learned risk classifier trained on the labeled `risk` field was considered and explicitly rejected per bootstrap SS9 ("Do NOT build a sophisticated learned risk model yet") — revisit only after this baseline's measured gaps (see Result below) justify it.

## Inputs / Outputs

Input: query string + `QueryFingerprint`. Output: `RiskProfile` (`risk_dimensions`, `severity`, `confidence`, `trigger_signals`, `recommended_control_depth`).

## Dataset

`query_profiles_validation` (28 examples) — only the aggregate `risk` field has ground truth; no per-dimension labels exist.

## Training / Fine-Tuning Requirement

None.

## Metrics

See `docs/EVALUATION/RISK_PROFILER_RESULTS.md`. Overall severity accuracy 60.7%, macro-F1 0.327. **The one true HIGH_RISK example in the validation split was missed** — a real, documented failure mode (decision-support/governance recommendations without agentic action or an obvious keyword don't currently escalate), not glossed over.

## Failure Modes

See the miss case above; also see `docs/PROJECT_STATE/PROGRESS.md` for the manual-verification finding that PII detection alone (reaching only MEDIUM_RISK) does not currently escalate `recommended_control_depth` to `DEEP_PATH` — a documented, intentional-but-worth-revisiting design choice (severity-gated, not dimension-gated).

## Result

Real signal above chance (60.7% vs. ~20% for 5 random classes) but not remotely sufficient on its own to gate a real HIGH_RISK/CRITICAL action — mitigated in practice by `PolicyBaseline`, which independently requires human approval at the HIGH_RISK/CRITICAL tier regardless of how the severity was reached.

## Final Decision

Adopted as the Milestone 2 baseline. The governance decision-support miss is recorded as the top priority for the next Risk Profiler iteration, ahead of any accuracy polish on already-covered categories.

## Version

v1 -- 2026-08-28.
