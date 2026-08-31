# controlplane/governance/

**Purpose:** a standalone Agent/Tool Governance gate  -  a pre-execution proposed-action risk check (`ALLOW`/`RESTRICT`/`HUMAN_REVIEW`/`BLOCK`). See `docs/ALGORITHMS/AGENT_GOVERNANCE.md`.

## Interface

- `agent_gate.py`: `GovernanceAction`, `GovernanceDecision` (`action`, `reason`, `triggering_signal`), `AgentGate.evaluate_step(tool_call, step_risk) -> GovernanceDecision`.

## Dependencies

None beyond the standard library  -  deterministic keyword/risk-label checks only.

## Limitations

**Not wired into any live execution path**  -  this repo's `AGENT` capability still executes via the `GraphExecutor`'s `MOCKED` handler, so there is no real agent proposing tool calls yet for this to gate. Evaluated against `data/raw/generated/agent_trajectories.json` (see `docs/EVALUATION/AGENT_GOVERNANCE_RESULTS.md`) as a standalone, measured decision function.

## Extension points

Once a real `AGENT` capability exists, its execution handler would call `AgentGate.evaluate_step` before each tool invocation and honor the returned `GovernanceAction`, the same way `controlplane.decision.engine` is honored by `controlplane.runtime`.
