# controlplane/policy/

**Purpose:** a small, configurable policy layer mapping risk severity to control requirements — not the full enterprise policy engine (`docs/architecture/PRODUCT_THESIS_UPDATED.md` §30), which is future work.

## Interface

`baseline.py`: `PolicyBaseline.decide(severity: RiskSeverity) -> PolicyDecision` (`tier`, `required_verification`, `human_approval_required`, `restricted_capabilities`, `reason`). Thresholds live in `PolicyBaseline.__init__`'s `_restricted_by_tier` mapping — configuration, not scattered `if`/`elif` chains through the runtime (bootstrap Rule 5).

## Dependencies

`controlplane.risk.profile.RiskSeverity` only.

## Limitations

Decides purely from the max risk severity, not from which specific dimension(s) drove it — a HIGH_RISK-via-safety-keyword and a HIGH_RISK-via-financial-keyword currently get identical policy treatment. Revisit once real policy requirements differentiate by dimension.

## Extension points

The full policy engine (per-application, per-jurisdiction, data-access rules) replaces `PolicyBaseline` behind the same `.decide(...)` shape when that work is scheduled.
