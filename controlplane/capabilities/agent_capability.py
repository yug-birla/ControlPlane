"""Real Agent/Tool capability -- the ``AGENT`` capability node's actual
handler, replacing the ``MOCKED`` handler used through Milestone 6.

Bootstrap: "AGENT PROPOSES ACTION -> CONTROLPLANE -> RISK -> POLICY ->
TRAJECTORY -> PERMISSION -> DECISION -> TOOL." This is that path, made
real: a small, fixed set of tools, each proposal gated live by
``controlplane.governance.agent_gate.AgentGate`` BEFORE it runs.

Tool selection is deterministic keyword-pattern matching against the
query text -- NOT an LLM decision. Same "never give an LLM unrestricted
tool-call authority" principle already established for the SQL
capability (``controlplane/capabilities/sql_capability.py``); an LLM
proposing arbitrary tool calls with no fixed vocabulary would defeat the
entire point of a governance gate sitting in front of it.

Tools:
- ``sql_read_query`` -- real, reuses the existing read-only
  ``SQLCapability`` (LOW_RISK).
- ``write_report`` -- real file write, sandboxed to
  ``data/agent_reports/`` (LOW_RISK).
- ``send_notification`` -- an external-destination action. The actual
  send is MOCKED (no real external channel is configured for this
  prototype -- stated plainly, not disguised as a real integration);
  the governance decision AROUND it is real (MEDIUM_RISK normally,
  HIGH_RISK when it mentions a high-stakes audience).
- ``destructive_operation`` -- a HARD constraint (bootstrap SS6:
  destructive-operation protection is never a semantic/graduated
  judgment call). Always ``BLOCKED``, unconditionally, regardless of
  what ``AgentGate``'s own graduated logic would otherwise decide --
  still routed through the gate so the attempt lands on the same audit
  trail as every other proposal, never silently bypassed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from controlplane.capabilities.sql_capability import SQLCapability
from controlplane.governance.agent_gate import AgentGate, GovernanceAction

_REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "agent_reports"

_DESTRUCTIVE_PATTERNS = re.compile(r"\b(drop|delete all|truncate|wipe|purge)\b", re.IGNORECASE)
_SQL_PATTERNS = re.compile(r"\b(how many|query|look ?up|count of|total number|revenue|database)\b", re.IGNORECASE)
_REPORT_PATTERNS = re.compile(r"\b(write (a |the )?report|generate (a |the )?report|summary (file|document)|save .* to (a )?file)\b", re.IGNORECASE)
_NOTIFY_PATTERNS = re.compile(r"\b(send|notify|email|share externally|post to)\b", re.IGNORECASE)
_HIGH_STAKES_NOTIFY_PATTERNS = re.compile(r"\b(board|investor|regulator|press release|public announcement|financial results)\b", re.IGNORECASE)


class AgentCapability:
    name = "agent_v0_gated_tools"

    def __init__(self, gate: AgentGate | None = None, sql_capability: SQLCapability | None = None) -> None:
        self._gate = gate or AgentGate()
        self._sql = sql_capability or SQLCapability()

    def _propose(self, query_text: str) -> tuple[str, str, str]:
        """Returns ``(tool_name, tool_call_description, step_risk)`` --
        deterministic pattern matching only, never an LLM decision."""
        if _NOTIFY_PATTERNS.search(query_text):
            tool_call = f"send_notification(query={query_text!r})"
            risk = "HIGH_RISK" if _HIGH_STAKES_NOTIFY_PATTERNS.search(query_text) else "MEDIUM_RISK"
            return "send_notification", tool_call, risk
        if _REPORT_PATTERNS.search(query_text):
            return "write_report", f"write_report(query={query_text!r})", "LOW_RISK"
        if _SQL_PATTERNS.search(query_text):
            return "sql_read_query", f"sql_read_query(query={query_text!r})", "LOW_RISK"
        return "no_actionable_tool", f"no_actionable_tool(query={query_text!r})", "NO_ACTION"

    def execute(self, query_text: str) -> dict:
        if _DESTRUCTIVE_PATTERNS.search(query_text):
            tool_call = f"destructive_operation(query={query_text!r})"
            # Still asked, purely for the audit record -- the outcome
            # below is hard-forced regardless of what it returns.
            self._gate.evaluate_step(tool_call, step_risk="CRITICAL")
            return {
                "status": "EXECUTED",
                "proposed_tool": "destructive_operation",
                "tool_call": tool_call,
                "step_risk": "CRITICAL",
                "governance_action": GovernanceAction.BLOCK.value,
                "governance_reason": "destructive operations are a hard constraint (bootstrap SS6) -- never executed regardless of any graduated risk judgment",
                "execution_status": "BLOCKED",
                "consequence_class": "HIGH_IMPACT_ACTION",
                "tool_result": {"status": "NOT_EXECUTED"},
            }

        tool_name, tool_call, step_risk = self._propose(query_text)
        decision = self._gate.evaluate_step(tool_call, step_risk=step_risk)

        result: dict = {
            "status": "EXECUTED",
            "proposed_tool": tool_name,
            "tool_call": tool_call,
            "step_risk": step_risk,
            "governance_action": decision.action.value,
            "governance_reason": decision.reason,
        }

        if decision.action == GovernanceAction.BLOCK:
            result["execution_status"] = "BLOCKED"
            result["consequence_class"] = "HIGH_IMPACT_ACTION"
            result["tool_result"] = {"status": "NOT_EXECUTED"}
            return result
        if decision.action == GovernanceAction.HUMAN_REVIEW:
            result["execution_status"] = "AWAITING_HUMAN_APPROVAL"
            result["consequence_class"] = "HIGH_IMPACT_ACTION"
            result["tool_result"] = {"status": "NOT_EXECUTED"}
            return result

        # ALLOW or RESTRICT both actually run the tool -- RESTRICT runs a
        # constrained (preview/no-real-side-effect) version, never
        # silently identical to ALLOW (bootstrap: "an intervention is
        # only valid if it actually changes behavior").
        restricted = decision.action == GovernanceAction.RESTRICT

        if tool_name == "sql_read_query":
            result["tool_result"] = self._sql.execute(query_text)
            result["consequence_class"] = "READ_ONLY"
        elif tool_name == "write_report":
            if restricted:
                result["tool_result"] = {"status": "PREVIEW_ONLY", "note": "RESTRICT: file not actually written"}
            else:
                path = self._write_report(query_text)
                result["tool_result"] = {"status": "WRITTEN", "path": str(path)}
            result["consequence_class"] = "REVERSIBLE_WRITE"
        elif tool_name == "send_notification":
            if restricted:
                result["tool_result"] = {"status": "QUEUED_FOR_REVIEW", "note": "RESTRICT: not actually sent"}
            else:
                result["tool_result"] = {
                    "status": "SENT",
                    "note": "MOCKED -- no real external notification channel is configured for this prototype",
                    "destination": "external_notification_channel",
                }
            result["consequence_class"] = "IRREVERSIBLE_WRITE"
        else:
            result["tool_result"] = {"status": "NO_OP"}
            result["consequence_class"] = "READ_ONLY"

        result["execution_status"] = "COMPLETED_RESTRICTED" if restricted else "COMPLETED"
        return result

    @staticmethod
    def _write_report(query_text: str) -> Path:
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = _REPORTS_DIR / f"report_{timestamp}.md"
        path.write_text(f"# Agent Report\n\nGenerated for query: {query_text}\n", encoding="utf-8")
        return path
