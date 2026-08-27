"""Baseline Risk Profiler: rules + Query Fingerprint + policy context.

bootstrap SS9 explicitly forbids a learned risk model at this milestone.
Every dimension's value traces to either a direct fingerprint field or a
named keyword trigger -- see ``trigger_signals`` on the returned
``RiskProfile``.
"""

from __future__ import annotations

import re

from controlplane.query_intelligence.fingerprint import (
    Actionability,
    Complexity,
    Impact,
    QueryFingerprint,
    Sensitivity,
)
from controlplane.risk.profile import ControlDepth, RiskProfile, RiskSeverity, max_severity

_FINANCIAL_KEYWORDS = ("refund", "payment", "invoice", "transfer", "budget", "reimburse", "payout")
_SECURITY_KEYWORDS = ("password", "credential", "api key", "access token", "admin", "bypass", "permission")
_BIAS_KEYWORDS = ("hire", "promote", "fire", "gender", "race", "age", "disability", "discriminat")
_SAFETY_KEYWORDS = ("harm", "illegal", "weapon", "exploit", "hack into", "self-harm")

_SENSITIVITY_TO_SEVERITY = {
    Sensitivity.NONE: RiskSeverity.NO_ACTION,
    Sensitivity.POTENTIAL_PII: RiskSeverity.MEDIUM_RISK,
    Sensitivity.PII_EXPOSURE: RiskSeverity.HIGH_RISK,
    Sensitivity.SENSITIVE_DATA_EXPOSURE: RiskSeverity.CRITICAL,
}

_IMPACT_TO_ACTION_SEVERITY = {
    Impact.LOW: RiskSeverity.NO_ACTION,
    Impact.MEDIUM: RiskSeverity.LOW_RISK,
    Impact.HIGH: RiskSeverity.HIGH_RISK,
    Impact.CRITICAL: RiskSeverity.CRITICAL,
}


def _keyword_hit(query_lower: str, *keywords: str) -> str | None:
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", query_lower):
            return kw
    return None


class BaselineRiskProfiler:
    name = "rules_and_fingerprint"

    def profile(self, query: str, fingerprint: QueryFingerprint) -> RiskProfile:
        q = query.lower()
        dims: dict[str, RiskSeverity] = {d: RiskSeverity.NO_ACTION for d in (
            "factuality", "reasoning", "privacy", "pii", "security", "bias", "financial", "action", "safety"
        )}
        confidence: dict[str, float] = {}
        triggers: list[str] = []

        # privacy/pii: directly from the fingerprint (already-detected sensitivity)
        sev = _SENSITIVITY_TO_SEVERITY[fingerprint.sensitivity]
        dims["privacy"] = sev
        dims["pii"] = sev
        if fingerprint.sensitivity != Sensitivity.NONE:
            confidence["privacy"] = 1.0
            confidence["pii"] = 1.0
            triggers.append(f"sensitivity={fingerprint.sensitivity.value}")

        # action: from impact + actionability
        action_sev = _IMPACT_TO_ACTION_SEVERITY[fingerprint.impact]
        if fingerprint.actionability == Actionability.AGENTIC:
            action_sev = max_severity(action_sev, RiskSeverity.MEDIUM_RISK)
            confidence["action"] = 1.0
            triggers.append(f"actionability={fingerprint.actionability.value}")
        dims["action"] = action_sev

        # factuality: ungrounded generation/analysis carries more factual risk
        if not fingerprint.data_requirement and fingerprint.intent.value in ("analytical", "reasoning", "decision_support", "generation"):
            dims["factuality"] = RiskSeverity.MEDIUM_RISK
            triggers.append("no data_requirement + generative/analytical intent")

        # reasoning: high complexity = more room for reasoning error
        if fingerprint.complexity == Complexity.HIGH:
            dims["reasoning"] = RiskSeverity.MEDIUM_RISK
            triggers.append("complexity=high")

        for dim, keywords in (("financial", _FINANCIAL_KEYWORDS), ("security", _SECURITY_KEYWORDS), ("bias", _BIAS_KEYWORDS)):
            hit = _keyword_hit(q, *keywords)
            if hit:
                base = RiskSeverity.HIGH_RISK if (dim == "financial" and fingerprint.actionability == Actionability.AGENTIC) else RiskSeverity.MEDIUM_RISK
                dims[dim] = base
                confidence[dim] = 1.0
                triggers.append(f"{dim} keyword {hit!r}")

        safety_hit = _keyword_hit(q, *_SAFETY_KEYWORDS)
        if safety_hit:
            dims["safety"] = RiskSeverity.HIGH_RISK
            confidence["safety"] = 1.0
            triggers.append(f"safety keyword {safety_hit!r}")

        overall = max_severity(*dims.values())
        control_depth = (
            ControlDepth.DEEP_PATH
            if overall in (RiskSeverity.HIGH_RISK, RiskSeverity.CRITICAL) or fingerprint.complexity == Complexity.HIGH
            else ControlDepth.FAST_PATH
        )

        return RiskProfile(
            risk_dimensions=dims,
            severity=overall,
            confidence=confidence,
            trigger_signals=triggers,
            recommended_control_depth=control_depth,
            source=self.name,
        )
