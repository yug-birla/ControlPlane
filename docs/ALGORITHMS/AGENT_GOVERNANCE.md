# Agent / Tool Governance Gate

**Status:** IMPLEMENTED and LIVE (Milestone 7, 2026-08-28; standalone gate was Milestone 6)

## Problem

Bootstrap SS32/SS24 (Milestone 7): a proposed agent tool call should pass through Risk → Policy → Decision → `ALLOW`/`RESTRICT`/`HUMAN_REVIEW`/`BLOCK` before executing, with unrestricted destructive actions never permitted — and this must actually be wired into a real execution path, not remain a standalone, ungated function.

## Architecture Location

`controlplane/governance/agent_gate.py` (the decision function, unchanged since Milestone 6) + `controlplane/capabilities/agent_capability.py` (**NEW this milestone** — the real tool-execution path that finally gates something). Wired into `controlplane/runtime.py::_execute_graph`'s handler dict for the `AGENT` capability node, replacing the `MOCKED` handler.

## Real Tools (NEW this milestone)

Deterministic keyword-pattern tool selection (never an LLM decision — same "no unrestricted LLM tool authority" principle as the SQL capability):

- `sql_read_query` — real, reuses the existing read-only `SQLCapability`.
- `write_report` — real sandboxed file write to `data/agent_reports/`.
- `send_notification` — governance is real; the external send itself is `MOCKED` (no real notification channel configured for this prototype — stated plainly).
- `destructive_operation` — a **hard constraint** (bootstrap SS6), always `BLOCK`ed unconditionally regardless of `AgentGate`'s own graduated logic — still routed through the gate so the attempt lands on the same audit trail.

## Three Real Bugs Found and Fixed Making This Live (error-driven development)

1. **AGENT was structurally unreachable.** Policy blanket-restricted `AGENT` at the `HIGH_RISK` tier (`controlplane/policy/baseline.py`), and any agentic-actionability query was *always* classified at least `HIGH_RISK` by the Risk Profiler's own design — so a real agentic request could never reach an ungated `AGENT` node; the Model Router could only `ABSTAIN`. Fixed: `HIGH_RISK` no longer restricts `AGENT` (only `CRITICAL_ACTION` does now) — the real gate handles the nuance instead of a blanket policy cutoff.
2. **"drop the customers table" never reached the AGENT capability at all.** `"drop"` was not in the Query Profiler's `_ACTION_KEYWORDS`, so the query was never classified agentic in the first place. Fixed with a proximity-aware regex (`\bdrop\b.{0,40}\b(table|database|...)\b`, avoiding the "a drop in revenue" false-positive a bare "drop" keyword would cause) plus adding `truncate`/`wipe`/`purge` as safe bare keywords.
3. **Trust/Verification/Decision never consumed the AGENT node's own governance outcome.** A real trace showed a HIGH_RISK tool proposal correctly reach `HUMAN_REVIEW` at the AgentCapability level while the query-level Risk Profiler had only assessed `MEDIUM_RISK` — and Trust reported `HIGH` anyway, since nothing downstream read the AGENT node's outcome. Fixed: `AgentGovernancePassthroughEvaluator` + a new Decision Engine hard-constraint branch (`agent_governance in (BLOCK, HUMAN_REVIEW)` → `HUMAN_REVIEW`), which correctly flows through to `Verification=REJECTED`/`Trust=LOW`.

## Method (Gate, unchanged from Milestone 6)

destructive-operation keyword match → `BLOCK`; `HIGH_RISK`/`CRITICAL` step risk → `HUMAN_REVIEW`; sensitive-data-access keyword match → `RESTRICT`; `MEDIUM_RISK` step risk → `RESTRICT`; otherwise → `ALLOW`.

## Real End-to-End Traces (all via the live runtime, not injected fakes)

| Query | Tool | Step Risk | Governance | Decision | Verification | Trust |
|---|---|---|---|---|---|---|
| "execute a database query to count support tickets" | `sql_read_query` | LOW_RISK | ALLOW | VERIFY | VERIFIED | HIGH/MEDIUM |
| "send a notification to the team about the routine update" | `send_notification` | MEDIUM_RISK | RESTRICT | VERIFY | VERIFIED | HIGH |
| "send a notification to the board about our financial results" | `send_notification` | HIGH_RISK | HUMAN_REVIEW | HUMAN_REVIEW | REJECTED | LOW |
| "drop the customers table from the database" | `destructive_operation` | CRITICAL | BLOCK | HUMAN_REVIEW | REJECTED | LOW |

Permanently regression-tested: `tests/test_control_loop_scenarios.py::test_agent_governed_action_is_allowed_and_reflected_as_high_trust`, `test_agent_governed_high_stakes_action_forces_human_review_and_low_trust`, `test_agent_governed_destructive_action_is_hard_blocked_end_to_end`.

## Candidate Alternatives

- **A learned classifier over `agent_trajectories.json`** — considered; rejected for an interpretable rule-based V0 (bootstrap SS11), dataset used for *evaluation*, not training.
- **Extending the gate to predict `CHANGE_DATA_SOURCE`/`DECREASE_COMPUTE`** — rejected: those are post-hoc recovery/cost decisions keyed to a tool call's *result*, not the proposed action's *inherent* risk.

## Inputs / Outputs

`AgentCapability.execute(query_text) -> dict` (proposed_tool, tool_call, step_risk, governance_action, governance_reason, execution_status, consequence_class, tool_result). `AgentGate.evaluate_step(tool_call, step_risk) -> GovernanceDecision`.

## Dataset

`data/raw/generated/agent_trajectories.json` — 75 trajectories, used for the standalone gate's evaluation (unchanged from Milestone 6, see `docs/EVALUATION/AGENT_GOVERNANCE_RESULTS.md`).

## Compute / Latency

Pure Python + one real SQLite query (for `sql_read_query`) or one real file write (for `write_report`) — negligible, no model call.

## Metrics

Gate accuracy 0.720/macro-F1 0.756 on 75 trajectories (unchanged, see `docs/EVALUATION/AGENT_GOVERNANCE_RESULTS.md`). New this milestone: 3/3 real end-to-end scenario tests pass, demonstrating all four governance outcomes reachable via the live `/v1/requests` path.

## Failure Modes

Same recovery-strategy scope gap as Milestone 6 (the gate has no signal for "this tool call's result was bad, try something else").

## Permission Lineage (bootstrap SS25, NEW this milestone)

`controlplane/dashboard/queries.py::get_request_detail` derives a `permission_lineage` view (`requested_tool`, `tool_call`, `authorization`, `authorization_reason`, `consequence_class`, `execution_status`, `accessed_resource`, `destination`) directly from the `AGENT` node's own trajectory step — the same "derive, don't duplicate storage" pattern already used for Trust (`docs/ALGORITHMS/TRUST_LAYER.md`): every field is already recorded by `AgentCapability`'s output, just not previously surfaced. Shown in the dashboard's per-request detail view. Verified: `tests/test_dashboard.py::test_dashboard_shows_agent_governance_and_permission_lineage`.

**Known limitation:** this is a single-hop lineage (one tool call per request, since only one `AGENT` node exists per graph currently) — not a multi-step USER→AGENT→AGENT→TOOL chain (bootstrap SS27's multi-agent composition is not attempted this milestone).

## Known Limitations

- `send_notification`'s actual send is `MOCKED` (no real external channel configured).
- Keyword-based tool selection and destructive-pattern detection, same class of brittleness as any keyword list.
- No trajectory-level accumulation across multiple agent actions in one request (only one `AGENT` node per graph currently) — see `docs/ALGORITHMS/BEHAVIORAL_DRIFT.md` for the separate, standalone cross-request drift baseline.

## Result

Agent Governance is now real, live, and reachable through the actual `/v1/requests` API path — not merely a standalone, tested-in-isolation function. Three real architectural bugs were found and fixed making it so, each via a genuine end-to-end trace, not assumed away.

## Final Decision

Adopted as the runtime default for the `AGENT` capability node.

## Version

v2 — 2026-08-28 (v1 was Milestone 6's standalone, unwired gate).
