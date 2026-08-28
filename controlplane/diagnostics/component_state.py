"""Component-level execution state and failure localization.

THE PROBLEM THIS SOLVES (stated directly in the Milestone 10 brief):
the system could report *that* a response failed, but not *which
component* failed and *why*. "verification = REJECTED" tells an operator
the outcome; it does not tell them whether the query was misunderstood,
the wrong capability was routed, the right evidence was never retrieved,
the retrieved evidence was ignored by the model, or the evaluator was
simply wrong.

DESIGN: DERIVE, DO NOT DUPLICATE.

Almost everything needed is already persisted -- trajectory steps (with
``started_at``/``completed_at``, status, and input/output refs),
``response_evaluations``, ``decisions``, ``verifications``, and
``model_invocations``. What was missing was not storage but
*correlation*: nothing assembled those rows into a per-component view,
and nothing attributed the final outcome to a specific component.

So this module adds no new table. It is the same pattern already used by
the Trust Layer (Milestone 6) and Permission Lineage (Milestone 7):
a derived, auditable view over data the runtime already writes.

STATUS VOCABULARY is the one the brief specifies, no more:
NOT_STARTED / RUNNING / COMPLETED / DEGRADED / FAILED / SKIPPED /
BLOCKED / RETRIED / REPLACED.

FAILURE LOCALIZATION is deliberately conservative. It reports the
EARLIEST component in the causal chain that can account for the observed
outcome, because attributing a bad answer to "generation" when the real
problem was that routing never retrieved any evidence is exactly the
mistake this module exists to prevent -- and is exactly the bug Milestone
9 found by hand (RAG routing recall 0.053, so ControlPlane returned the
unmanaged model's answer verbatim while every component "succeeded").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ComponentStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    RETRIED = "RETRIED"
    REPLACED = "REPLACED"


class Component(str, Enum):
    """The components an operator can meaningfully attribute a failure to.

    Intentionally coarser than the module list: an operator asking "where
    did this go wrong?" needs actionable buckets, not every class in the
    codebase.
    """

    QUERY_PROFILER = "QUERY_PROFILER"
    RISK_PROFILER = "RISK_PROFILER"
    POLICY = "POLICY"
    CAPABILITY_ROUTER = "CAPABILITY_ROUTER"
    MODEL_ROUTER = "MODEL_ROUTER"
    RETRIEVAL = "RETRIEVAL"
    SQL = "SQL"
    AGENT = "AGENT"
    GENERATION = "GENERATION"
    EVALUATION = "EVALUATION"
    DECISION = "DECISION"
    INTERVENTION = "INTERVENTION"
    REPLAN = "REPLAN"
    VERIFICATION = "VERIFICATION"
    TRUST = "TRUST"


# Not a component failure: the request itself was hostile or
# out-of-scope, and the system behaving correctly means refusing or
# escalating it. Attributing these to a component would make correct
# governance look like a defect.
class Attribution(str, Enum):
    COMPONENT_FAILURE = "COMPONENT_FAILURE"
    INPUT_GOVERNED = "INPUT_GOVERNED"
    NO_FAILURE = "NO_FAILURE"
    UNDETERMINED = "UNDETERMINED"


@dataclass
class ComponentReport:
    component: Component
    status: ComponentStatus
    summary: str = ""
    signal: str | None = None
    """The component's own headline output (e.g. "HIGH_RISK", "SUPPORTED",
    "RETRIEVE_MORE") -- what it concluded, not how it concluded it."""
    latency_ms: int | None = None
    error: str | None = None
    decision_impact: str | None = None
    """What this component's output caused downstream. Empty when it had
    no effect on the outcome."""

    def to_dict(self) -> dict:
        return {
            "component": self.component.value,
            "status": self.status.value,
            "summary": self.summary,
            "signal": self.signal,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "decision_impact": self.decision_impact,
        }


@dataclass
class FailureLocalization:
    attribution: Attribution
    component: Component | None = None
    reason: str = ""
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "attribution": self.attribution.value,
            "component": self.component.value if self.component else None,
            "reason": self.reason,
            "evidence": self.evidence,
        }


# Evaluator name -> the component whose output that evaluator judges.
# Used to attribute a failing evaluation to the thing that produced the
# artifact, not to the evaluator that noticed.
_EVALUATOR_TO_SOURCE: dict[str, Component] = {
    "grounding": Component.GENERATION,
    "factuality": Component.GENERATION,
    "reasoning": Component.GENERATION,
    "response_confidence": Component.GENERATION,
    "rag_adequacy": Component.RETRIEVAL,
    "agent_governance": Component.AGENT,
}

# Evaluators that flag a property of the REQUEST, not of any component's
# work. A flag here means the system correctly governed hostile or
# high-impact input.
_INPUT_EVALUATORS = {"prompt_injection", "safety", "action_risk", "privacy_pii"}


def localize_failure(
    *,
    evaluations: list[dict],
    decision: dict | None,
    verification: dict | None,
    retrieval_ran: bool,
    evidence_count: int,
    failed_steps: list[str],
) -> FailureLocalization:
    """Attribute an outcome to the earliest component that explains it.

    ``evaluations`` are the persisted evaluation rows (each with
    ``evaluator``, ``label``, ``recommended_signal``).
    """
    # 1. A component that actually threw is unambiguous, and beats any
    #    inference from evaluator labels.
    if failed_steps:
        step = failed_steps[0]
        return FailureLocalization(
            attribution=Attribution.COMPONENT_FAILURE,
            component=_component_for_step(step),
            reason=f"execution step {step!r} failed",
            evidence={"failed_steps": failed_steps},
        )

    flagged = [
        e for e in evaluations
        if e.get("recommended_signal") in ("FLAG_FOR_REVIEW", "BLOCK")
    ]

    # 2. Hostile / high-impact input that the system correctly governed
    #    is NOT a component failure. Checked before the quality
    #    evaluators so that a blocked injection isn't misreported as a
    #    generation defect.
    input_flags = [e for e in flagged if e.get("evaluator") in _INPUT_EVALUATORS]
    if input_flags:
        return FailureLocalization(
            attribution=Attribution.INPUT_GOVERNED,
            component=None,
            reason="request was flagged and governed: "
                   + ", ".join(f"{e['evaluator']}={e.get('label')}" for e in input_flags),
            evidence={"evaluators": [e["evaluator"] for e in input_flags]},
        )

    quality_flags = [e for e in flagged if e.get("evaluator") not in _INPUT_EVALUATORS]
    if quality_flags:
        first = quality_flags[0]
        evaluator = first.get("evaluator", "")
        source = _EVALUATOR_TO_SOURCE.get(evaluator, Component.GENERATION)

        # THE KEY CASE, and the reason this function is conservative:
        # an ungrounded answer when NO retrieval ran is a ROUTING
        # failure, not a generation failure. The model was never given
        # anything to ground against. Blaming generation here is what
        # hid the Milestone 9 routing bug (recall 0.053) behind
        # "every component completed successfully".
        if source in (Component.GENERATION, Component.RETRIEVAL) and not retrieval_ran:
            return FailureLocalization(
                attribution=Attribution.COMPONENT_FAILURE,
                component=Component.CAPABILITY_ROUTER,
                reason=(
                    f"{evaluator}={first.get('label')} but no retrieval node ran -- "
                    "the model was never given evidence to ground against, so this is a "
                    "routing failure upstream of generation, not a generation failure"
                ),
                evidence={"evaluator": evaluator, "retrieval_ran": False},
            )

        # Retrieval ran but returned nothing usable -> retrieval, not generation.
        if retrieval_ran and evidence_count == 0:
            return FailureLocalization(
                attribution=Attribution.COMPONENT_FAILURE,
                component=Component.RETRIEVAL,
                reason=f"{evaluator}={first.get('label')} and retrieval returned no evidence",
                evidence={"evaluator": evaluator, "evidence_count": 0},
            )

        return FailureLocalization(
            attribution=Attribution.COMPONENT_FAILURE,
            component=source,
            reason=f"{evaluator}={first.get('label')} with evidence available "
                   f"({evidence_count} item(s)) -- the artifact itself is at fault",
            evidence={"evaluator": evaluator, "evidence_count": evidence_count},
        )

    # 3. Verification failed with nothing flagged: the verifier and the
    #    evaluators disagree. Say so rather than inventing a culprit.
    status = (verification or {}).get("status")
    if status in ("REJECTED", "NOT_VERIFIED"):
        return FailureLocalization(
            attribution=Attribution.UNDETERMINED,
            component=Component.VERIFICATION,
            reason=f"verification={status} but no evaluator flagged a problem -- "
                   "verification and evaluation disagree",
            evidence={"verification_status": status},
        )

    return FailureLocalization(attribution=Attribution.NO_FAILURE, reason="no failure detected")


_STEP_TO_COMPONENT = {
    "query_profiling": Component.QUERY_PROFILER,
    "risk_assessment": Component.RISK_PROFILER,
    "routing": Component.CAPABILITY_ROUTER,
    "generation": Component.GENERATION,
    "evaluation": Component.EVALUATION,
    "model_invocation": Component.GENERATION,
}


def _component_for_step(step_type: str) -> Component:
    if step_type in _STEP_TO_COMPONENT:
        return _STEP_TO_COMPONENT[step_type]
    # Graph node steps are named "route:<node_id>" (e.g. route:data_rag).
    if step_type.startswith("route:"):
        node = step_type.split(":", 1)[1]
        if "rag" in node:
            return Component.RETRIEVAL
        if "sql" in node:
            return Component.SQL
        if "agent" in node:
            return Component.AGENT
        if "generation" in node:
            return Component.GENERATION
    return Component.GENERATION
