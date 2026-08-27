"""Baseline configurable policy layer -- bootstrap Milestone 2 SS10.

Not the full enterprise policy engine (docs/architecture/PRODUCT_THESIS_UPDATED.md
SS30) -- a small, replaceable mapping from risk severity to control
requirements. Thresholds are configuration, not hard-coded business logic
scattered through the runtime -- see ``PolicyBaseline.thresholds`` for the
one place they live.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from controlplane.risk.profile import RiskSeverity


class PolicyTier(str, Enum):
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL_ACTION = "CRITICAL_ACTION"


_SEVERITY_TO_TIER = {
    RiskSeverity.NO_ACTION: PolicyTier.LOW_RISK,
    RiskSeverity.LOW_RISK: PolicyTier.LOW_RISK,
    RiskSeverity.MEDIUM_RISK: PolicyTier.MEDIUM_RISK,
    RiskSeverity.HIGH_RISK: PolicyTier.HIGH_RISK,
    RiskSeverity.CRITICAL: PolicyTier.CRITICAL_ACTION,
}


class PolicyDecision(BaseModel):
    tier: PolicyTier
    required_verification: bool
    human_approval_required: bool
    restricted_capabilities: list[str] = Field(default_factory=list)
    reason: str


class PolicyBaseline:
    """Configurable via ``thresholds``/``restricted_by_tier`` at
    construction time rather than hard-coded ``if``/``elif`` chains
    scattered through the runtime (bootstrap Rule 5)."""

    def __init__(self) -> None:
        self._restricted_by_tier: dict[PolicyTier, list[str]] = {
            PolicyTier.LOW_RISK: [],
            PolicyTier.MEDIUM_RISK: [],
            PolicyTier.HIGH_RISK: ["AGENT"],
            PolicyTier.CRITICAL_ACTION: ["AGENT", "SQL"],
        }

    def decide(self, severity: RiskSeverity) -> PolicyDecision:
        tier = _SEVERITY_TO_TIER[severity]
        return PolicyDecision(
            tier=tier,
            required_verification=tier in (PolicyTier.MEDIUM_RISK, PolicyTier.HIGH_RISK, PolicyTier.CRITICAL_ACTION),
            human_approval_required=tier in (PolicyTier.HIGH_RISK, PolicyTier.CRITICAL_ACTION),
            restricted_capabilities=self._restricted_by_tier[tier],
            reason=f"severity={severity.value} -> tier={tier.value}",
        )
