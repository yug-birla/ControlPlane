"""Agent/Tool Governance gate -- bootstrap SS32: "AGENT PROPOSES ACTION
-> CONTROLPLANE -> RISK -> POLICY -> TRAJECTORY -> DECISION -> ALLOW /
RESTRICT / HUMAN / BLOCK -> TOOL -> RESULT -> LEDGER -> VERIFY."

STANDALONE, not yet wired into a live AGENT capability node: this
repo's AGENT capability still executes via the ``GraphExecutor``'s
explicit MOCKED handler (Layer 5/18 -- see
docs/PROJECT_STATE/FUTURE_WORK.md), so there is no real agent actually
proposing/executing tool calls in the live runtime yet for this to gate.
This is a real, tested, measured decision function --
``controlplane/experiments/evaluate_agent_governance.py`` scores it
against ``data/raw/generated/agent_trajectories.json``'s real
``expected_control_action`` labels (75 trajectories) -- ready to be the
actual gate once a real agent/tool execution path exists. Stated plainly
per bootstrap SS65 ("never claim autonomous recovery/governance if it
doesn't actually execute yet").

Deliberately narrow: this is a PRE-EXECUTION proposed-action risk gate
(destructive-operation keywords, sensitive-data-access keywords, step
risk severity) -- not a post-hoc recovery-strategy selector. It does not
attempt to predict "switch to a different data source after this tool
call failed" or "this trajectory is running unnecessarily expensive
compute" (the dataset's CHANGE_DATA_SOURCE/DECREASE_COMPUTE labels);
those are execution-outcome/cost decisions that belong to
Replanning/Intervention, not an authorization gate over a proposed
action. See docs/EVALUATION/AGENT_GOVERNANCE_RESULTS.md for where this
gate's 4-action vocabulary agrees and disagrees with the dataset's
6-value vocabulary, and why.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class GovernanceAction(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    BLOCK = "BLOCK"


class GovernanceDecision(BaseModel):
    action: GovernanceAction
    reason: str
    triggering_signal: str | None = None
    gate_version: str = "agent_gate_v0"


_DESTRUCTIVE_KEYWORDS = (
    "drop table", "delete from", "truncate", "rm -rf", "format c:", "delete all", "wipe",
)
_SENSITIVE_ACCESS_KEYWORDS = (
    "ssn", "social security", "credit card", "password", "api_key", "api key", "secret",
)


class AgentGate:
    name = "agent_gate_v0"

    def evaluate_step(self, tool_call: str, step_risk: str | None = None) -> GovernanceDecision:
        lowered = tool_call.lower()

        if any(k in lowered for k in _DESTRUCTIVE_KEYWORDS):
            return GovernanceDecision(
                action=GovernanceAction.BLOCK,
                reason=f"tool call matches a destructive-operation pattern: {tool_call!r}",
                triggering_signal="destructive_keyword",
            )

        if step_risk in ("HIGH_RISK", "CRITICAL"):
            return GovernanceDecision(
                action=GovernanceAction.HUMAN_REVIEW,
                reason=f"step risk={step_risk} requires human sign-off before this action proceeds",
                triggering_signal="step_risk",
            )

        if any(k in lowered for k in _SENSITIVE_ACCESS_KEYWORDS):
            return GovernanceDecision(
                action=GovernanceAction.RESTRICT,
                reason=f"tool call references sensitive data access: {tool_call!r}",
                triggering_signal="sensitive_access_keyword",
            )

        if step_risk == "MEDIUM_RISK":
            return GovernanceDecision(
                action=GovernanceAction.RESTRICT,
                reason=f"step risk={step_risk} -- proceed in a restricted (read-only/draft-only) mode",
                triggering_signal="step_risk",
            )

        return GovernanceDecision(
            action=GovernanceAction.ALLOW,
            reason="no destructive/sensitive-access/elevated-risk signal found",
            triggering_signal=None,
        )
