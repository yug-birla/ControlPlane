"""Risk Profile schema and severity scale.

``RiskSeverity`` reuses the 5-value scale already established throughout
``docs/DATA/ANNOTATION_GUIDELINES.md``, ``data/schemas/query_profile.schema.json``
(field ``risk``), and ``docs/DATA/POSTGRES_SCHEMA.md`` (``annotations.action_risk``)
-- a fourth risk scale was not introduced (see docs/PROJECT_STATE/DECISIONS.md).
``recommended_control_depth`` reuses the Fast Path / Deep Path vocabulary
already defined in ``docs/architecture/RUNTIME_FLOW.md``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskSeverity(str, Enum):
    NO_ACTION = "NO_ACTION"
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"


_ORDER = [RiskSeverity.NO_ACTION, RiskSeverity.LOW_RISK, RiskSeverity.MEDIUM_RISK, RiskSeverity.HIGH_RISK, RiskSeverity.CRITICAL]


def max_severity(*values: RiskSeverity) -> RiskSeverity:
    return max(values, key=_ORDER.index) if values else RiskSeverity.NO_ACTION


class ControlDepth(str, Enum):
    FAST_PATH = "FAST_PATH"
    DEEP_PATH = "DEEP_PATH"


RISK_DIMENSIONS = (
    "factuality",
    "reasoning",
    "privacy",
    "pii",
    "security",
    "bias",
    "financial",
    "action",
    "safety",
)


class RiskProfile(BaseModel):
    risk_dimensions: dict[str, RiskSeverity]
    """One entry per name in RISK_DIMENSIONS -- never a single opaque
    number (bootstrap SS9: "Do not convert everything into one opaque
    number.")."""
    severity: RiskSeverity
    """max() across risk_dimensions -- the single value used for routing
    decisions, always traceable back to which dimension(s) drove it via
    trigger_signals."""
    confidence: dict[str, float] = Field(default_factory=dict)
    """Only for dimensions where a specific rule actually fired.
    Deliberately absent for dimensions that defaulted to NO_ACTION/LOW_RISK
    with no trigger -- absence of a detected signal is not evidence of
    safety, so it is never reported as a confident "safe" score."""
    trigger_signals: list[str] = Field(default_factory=list)
    recommended_control_depth: ControlDepth
    source: str = "rules_and_fingerprint"
