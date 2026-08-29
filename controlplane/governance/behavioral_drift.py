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

# Ordering for taking the max of two levels. Declared explicitly rather
# than relying on the enum's declaration order, which is not a contract.
_LEVEL_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


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

    def __init__(self, rare_tool_threshold: float = 0.1, severity_aware: bool = True) -> None:
        """``severity_aware`` (v2) makes ``DriftLevel.HIGH`` reachable.

        THE DEFECT IT ADDRESSES. The level was derived purely from HOW
        MANY of two signals fired, so it saturated at MEDIUM and HIGH
        could never be emitted at all -- measured on 22 longitudinal
        trajectories as precision 0.000 / recall 0.000 for that class,
        with all six HIGH cases (unprecedented wire transfer, privilege
        escalation, destructive action, bulk external export) downgraded.
        Any consumer branching on HIGH was dead code.

        Counting signals treats "this tool is new" and "the governance
        layer would not permit this outright" as interchangeable
        evidence. They are not. An action the governance layer refuses,
        on a tool this trajectory has never used, is the strongest drift
        signal available -- and that is a statement about consequence,
        not a threshold fitted to a label set.

        ADOPTED 2026-08-30 on measured evidence, 22 longitudinal cases
        with a stratified dev/test split:

                            v1 (count)   v2 (severity-aware)
          dev  exact           0.333          0.500
          TEST exact           0.500          0.800
          TEST macro-F1        0.423          0.756
          HIGH class f1        0.000          0.909
          false alarms             0              0
          missed drift             5              5

        It improves on both splits, gains MORE on the held-out one than
        on the tuning one, and costs nothing: no new false alarms and no
        additional misses.

        WHAT IT DOES NOT FIX. Alert-decision accuracy is unchanged at
        0.773. The five still-missed cases are gradual creep, changed
        destination, and read-only-to-mutating transitions -- none of
        which the (tool, governance_action) representation carries at
        all. This makes the LEVEL correct; it does not widen what the
        detector can see. That remains open in FUTURE_WORK."""
        self._rare_tool_threshold = rare_tool_threshold
        self._severity_aware = severity_aware

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

        if self._severity_aware and signals:
            # Weight by CONSEQUENCE, not just by how many signals fired.
            # An action the governance layer will not permit outright is
            # categorically more serious than an unfamiliar-but-allowed
            # one, however many frequency signals each happens to trip.
            unprecedented = tool_frequency == 0.0
            if this_severity >= _GOVERNANCE_SEVERITY_RANK["HUMAN_REVIEW"] and unprecedented:
                level = DriftLevel.HIGH
                reason = (
                    f"governance_action={governance_action} on a tool never seen in this "
                    f"trajectory -- highest-consequence drift signal; " + "; ".join(signals)
                )
            elif this_severity >= _GOVERNANCE_SEVERITY_RANK["HUMAN_REVIEW"]:
                level = max(level, DriftLevel.MEDIUM, key=_LEVEL_ORDER.__getitem__)
                reason = f"governance_action={governance_action} is high-consequence; " + "; ".join(signals)

        return DriftAssessment(level=level, reason=reason, signals=signals, baseline_sample_count=total)
