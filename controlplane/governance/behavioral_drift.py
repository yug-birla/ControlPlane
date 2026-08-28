"""Behavioral Drift -- bootstrap SS26: compare an observed trajectory
against a baseline of "normal" recent patterns; drift is a signal, not
an automatic block ("DRIFT + RISK + POLICY + IMPACT -> CONTROL DECISION").

Scope, stated honestly: this is a REAL, tested, working detector -- not
yet wired into the live per-request Decision Engine. Doing that would
require a DB query per request against real historical volume this
prototype doesn't yet have (a handful of demo/test requests is not a
meaningful "normal" baseline to compare against; flagging drift against
an near-empty or arbitrary baseline would be worse than not flagging at
all). It is exposed as an informational, on-demand signal
(``controlplane/experiments/evaluate_behavioral_drift.py`` demonstrates
it against a realistic synthetic history), ready to wire into the live
Decision Engine once real usage volume exists to baseline against --
the same "standalone until a live path justifies it" pattern already
used for ``controlplane.governance.agent_gate.AgentGate`` before this
milestone's AgentCapability gave it one.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum

from pydantic import BaseModel, Field

_GOVERNANCE_SEVERITY_RANK = {"ALLOW": 0, "RESTRICT": 1, "HUMAN_REVIEW": 2, "BLOCK": 3}


class DriftLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DriftAssessment(BaseModel):
    level: DriftLevel
    reason: str
    signals: list[str] = Field(default_factory=list)
    baseline_sample_count: int


class BehavioralDriftDetector:
    """A minimal, interpretable baseline (bootstrap SS11): frequency of
    the proposed tool in recent history, and whether its governance
    outcome is more severe than the historical norm. Not a learned
    anomaly model -- no training data exists for one yet."""

    name = "behavioral_drift_v0"

    def __init__(self, rare_tool_threshold: float = 0.1) -> None:
        self._rare_tool_threshold = rare_tool_threshold

    def assess(
        self,
        history: list[tuple[str, str]],
        proposed_tool: str,
        governance_action: str,
    ) -> DriftAssessment:
        """``history`` is a list of ``(tool, governance_action)`` pairs
        from recent past requests, oldest-first-or-any-order (order
        doesn't matter for this frequency-based baseline)."""
        if not history:
            return DriftAssessment(
                level=DriftLevel.NONE, reason="no history available to compare against",
                baseline_sample_count=0,
            )

        tool_counts = Counter(t for t, _ in history)
        total = len(history)
        tool_frequency = tool_counts.get(proposed_tool, 0) / total

        signals = []
        if tool_frequency <= self._rare_tool_threshold:
            signals.append(f"tool {proposed_tool!r} appears in only {tool_frequency:.0%} of recent history")

        historical_max_severity = max(
            (_GOVERNANCE_SEVERITY_RANK.get(g, 0) for _, g in history), default=0
        )
        this_severity = _GOVERNANCE_SEVERITY_RANK.get(governance_action, 0)
        if this_severity > historical_max_severity:
            signals.append(
                f"governance_action={governance_action} is more severe than any recent outcome "
                f"(historical max severity rank={historical_max_severity})"
            )

        if not signals:
            level = DriftLevel.NONE
            reason = "consistent with recent trajectory patterns"
        elif len(signals) == 1:
            level = DriftLevel.LOW
            reason = signals[0]
        else:
            level = DriftLevel.MEDIUM
            reason = "; ".join(signals)

        return DriftAssessment(level=level, reason=reason, signals=signals, baseline_sample_count=total)
