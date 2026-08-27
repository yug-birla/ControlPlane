"""Model Router -- V0 threshold baseline per
docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md SS17 ("STATE -> ACTION",
not a plain query->model classifier) and bootstrap SS35.

Only the actions this milestone can actually execute are implemented:
``USE_FAST_MODEL``, ``USE_STRONG_MODEL``, ``HUMAN_REVIEW`` (draft
generated with the strongest model, but the decision itself -- not just
a downstream action -- requires human sign-off), and ``ABSTAIN`` (the
one case where generating any answer would misrepresent what actually
happened: an agentic request whose AGENT capability policy already
restricted). ``CONTINUE_CURRENT_MODEL``/``SWITCH_MODEL``/cascading are
out of scope until a multi-turn/cascade runtime exists (P1, spec SS41).

FAST vs STRONG model identity is resolved by ``controlplane.models.registry
.get_configured_provider(settings, role=...)`` -- this module never
imports a model name or SDK.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from controlplane.policy.baseline import PolicyDecision, PolicyTier
from controlplane.query_intelligence.fingerprint import Actionability, Complexity, Impact, QueryFingerprint
from controlplane.risk.profile import RiskProfile, RiskSeverity


class ModelRouteAction(str, Enum):
    USE_FAST_MODEL = "USE_FAST_MODEL"
    USE_STRONG_MODEL = "USE_STRONG_MODEL"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    ABSTAIN = "ABSTAIN"


class ModelRouteDecision(BaseModel):
    action: ModelRouteAction
    model_role: str | None
    """"FAST" | "STRONG" | None (None only for ABSTAIN -- no generation
    call happens)."""
    require_verification: bool
    human_approval_required: bool
    reason: str
    expected_cost_class: str
    """ESTIMATE, not measured -- see capability_router.py's identical caveat."""
    expected_latency_class: str
    router_version: str = "v0"


class ModelRouter:
    name = "threshold_v0"

    def decide(
        self, fingerprint: QueryFingerprint, risk: RiskProfile, policy: PolicyDecision
    ) -> ModelRouteDecision:
        if fingerprint.actionability == Actionability.AGENTIC and "AGENT" in policy.restricted_capabilities:
            return ModelRouteDecision(
                action=ModelRouteAction.ABSTAIN,
                model_role=None,
                require_verification=False,
                human_approval_required=policy.human_approval_required,
                reason=(
                    f"actionability=agentic but AGENT is restricted at policy tier {policy.tier.value} "
                    "-- generating a response could misrepresent an action that cannot actually be performed"
                ),
                expected_cost_class="NONE",
                expected_latency_class="NONE",
            )

        if policy.tier in (PolicyTier.HIGH_RISK, PolicyTier.CRITICAL_ACTION):
            return ModelRouteDecision(
                action=ModelRouteAction.HUMAN_REVIEW,
                model_role="STRONG",
                require_verification=True,
                human_approval_required=True,
                reason=f"policy_tier={policy.tier.value} requires human approval before this can be treated as final",
                expected_cost_class="HIGH",
                expected_latency_class="HIGH",
            )

        if fingerprint.impact in (Impact.HIGH, Impact.CRITICAL):
            return ModelRouteDecision(
                action=ModelRouteAction.USE_STRONG_MODEL,
                model_role="STRONG",
                require_verification=True,
                human_approval_required=False,
                reason=f"impact={fingerprint.impact.value} -- strongest available model plus mandatory verification",
                expected_cost_class="HIGH",
                expected_latency_class="HIGH",
            )

        if fingerprint.complexity == Complexity.HIGH:
            return ModelRouteDecision(
                action=ModelRouteAction.USE_STRONG_MODEL,
                model_role="STRONG",
                require_verification=policy.required_verification,
                human_approval_required=False,
                reason="complexity=high -- routed to the strong model",
                expected_cost_class="HIGH",
                expected_latency_class="HIGH",
            )

        if fingerprint.complexity == Complexity.LOW and risk.severity in (RiskSeverity.NO_ACTION, RiskSeverity.LOW_RISK):
            return ModelRouteDecision(
                action=ModelRouteAction.USE_FAST_MODEL,
                model_role="FAST",
                require_verification=False,
                human_approval_required=False,
                reason=f"complexity=low, risk={risk.severity.value} -- fast model, no verification needed",
                expected_cost_class="LOW",
                expected_latency_class="LOW",
            )

        return ModelRouteDecision(
            action=ModelRouteAction.USE_FAST_MODEL,
            model_role="FAST",
            require_verification=policy.required_verification,
            human_approval_required=False,
            reason=(
                f"complexity={fingerprint.complexity.value}, risk={risk.severity.value} -- "
                "default to fast model; verification follows policy"
            ),
            expected_cost_class="LOW",
            expected_latency_class="MEDIUM" if policy.required_verification else "LOW",
        )
