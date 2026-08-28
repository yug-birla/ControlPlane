"""Trust Layer -- bootstrap SS36: "Do NOT invent arbitrary percentages.
Trust should depend on evidence such as: verification result, evaluator
agreement, evidence support, risk, data quality, model reliability,
intervention outcome. Output: HIGH/MEDIUM/LOW plus WHY and supporting
evidence."

A pure, deterministic composition of signals the rest of the control
loop already computed and persisted -- Verification's own status, the
Decision Engine's terminal action/attempt count, and Risk severity. No
new score is invented from scratch; this only orders/caps existing
verdicts into one final level with a stated reason, per bootstrap's own
warning against fabricated confidence numbers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from controlplane.decision.engine import ControlDecision
from controlplane.risk.profile import RiskProfile, RiskSeverity
from controlplane.verification.engine import VerificationResult, VerificationStatus


class TrustLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TrustAssessment(BaseModel):
    level: TrustLevel
    reason: str
    contributing_factors: list[str] = Field(default_factory=list)
    trust_version: str = "trust_v0"


class TrustEngine:
    name = "trust_v0"

    def assess(self, verification: VerificationResult, decision: ControlDecision, risk: RiskProfile) -> TrustAssessment:
        factors = [
            f"verification={verification.status.value}",
            f"decision_action={decision.action.value}",
            f"risk_severity={risk.severity.value}",
            f"attempt_number={decision.attempt_number}",
        ]

        if verification.status == VerificationStatus.REJECTED:
            return TrustAssessment(
                level=TrustLevel.LOW,
                reason="verification REJECTED -- requires human approval before this result can be trusted",
                contributing_factors=factors,
            )
        if verification.status == VerificationStatus.NOT_VERIFIED:
            return TrustAssessment(
                level=TrustLevel.LOW,
                reason=f"verification NOT_VERIFIED: {verification.reason}",
                contributing_factors=factors,
            )
        if risk.severity in (RiskSeverity.HIGH_RISK, RiskSeverity.CRITICAL):
            return TrustAssessment(
                level=TrustLevel.MEDIUM,
                reason=f"verification passed, but underlying risk severity is {risk.severity.value} -- capped below HIGH regardless of verification outcome",
                contributing_factors=factors,
            )
        if verification.status == VerificationStatus.PARTIALLY_VERIFIED:
            return TrustAssessment(
                level=TrustLevel.MEDIUM,
                reason=f"verification PARTIALLY_VERIFIED: {verification.reason}",
                contributing_factors=factors,
            )
        if decision.attempt_number > 1:
            return TrustAssessment(
                level=TrustLevel.MEDIUM,
                reason="verification VERIFIED, but only after at least one intervention/retry -- one notch below a clean first-pass VERIFIED",
                contributing_factors=factors,
            )
        return TrustAssessment(
            level=TrustLevel.HIGH,
            reason="verification VERIFIED on the first attempt with no elevated risk",
            contributing_factors=factors,
        )
