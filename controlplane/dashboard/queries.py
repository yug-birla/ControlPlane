"""Read-only queries backing the dashboard. Never writes anything --
this module only ever runs SELECTs against ControlPlane's own operational
tables (never the SQL capability's separate NexaConsult SQLite demo
data, which has nothing to do with dashboard observability)."""

from __future__ import annotations

from sqlalchemy import desc, select

from controlplane.db.engine import session_scope
from controlplane.db.models import (
    DecisionRecord,
    EventRecord,
    ExecutionLedgerRecord,
    InterventionRecord,
    ModelInvocationRecord,
    QueryProfileRecord,
    ReplanRecord,
    RequestRecord,
    ResponseEvaluationRecord,
    RouteDecisionRecord,
    TrajectoryRecord,
    TrajectoryStepRecord,
    VerificationRecord,
)
from controlplane.decision.engine import ControlDecision
from controlplane.risk.profile import RiskProfile
from controlplane.diagnostics.report import build_component_reports, localize
from controlplane.trust.engine import TrustEngine
from controlplane.verification.engine import VerificationResult

_QUERY_PREVIEW_LEN = 120


def list_recent_requests(limit: int = 50) -> list[dict]:
    """3 queries total regardless of ``limit`` -- an earlier version
    issued 2 extra queries per request (N+1), found during this
    milestone's mandatory architecture audit while explaining an
    unexpectedly slow dashboard test run. Batches profiles/routes for
    all listed requests in one query each instead."""
    with session_scope() as session:
        requests = session.execute(
            select(RequestRecord).order_by(desc(RequestRecord.created_at)).limit(limit)
        ).scalars().all()
        if not requests:
            return []
        request_ids = [r.id for r in requests]

        profiles_by_request: dict[str, QueryProfileRecord] = {}
        for p in session.execute(
            select(QueryProfileRecord)
            .where(QueryProfileRecord.request_id.in_(request_ids))
            .order_by(desc(QueryProfileRecord.created_at))
        ).scalars():
            profiles_by_request.setdefault(p.request_id, p)  # first seen = latest, thanks to the ORDER BY

        routes_by_request: dict[str, RouteDecisionRecord] = {}
        for r in session.execute(
            select(RouteDecisionRecord)
            .where(RouteDecisionRecord.request_id.in_(request_ids))
            .order_by(desc(RouteDecisionRecord.created_at))
        ).scalars():
            routes_by_request.setdefault(r.request_id, r)

        verifications_by_request: dict[str, VerificationRecord] = {}
        for v in session.execute(
            select(VerificationRecord)
            .where(VerificationRecord.request_id.in_(request_ids))
            .order_by(desc(VerificationRecord.created_at))
        ).scalars():
            verifications_by_request.setdefault(v.request_id, v)

        intervened_requests: set[str] = set(
            session.execute(
                select(InterventionRecord.request_id).where(InterventionRecord.request_id.in_(request_ids))
            ).scalars()
        )

        rows = []
        for req in requests:
            profile = profiles_by_request.get(req.id)
            route = routes_by_request.get(req.id)
            verification = verifications_by_request.get(req.id)

            rows.append({
                "request_id": req.id,
                "query_preview": req.query_text[:_QUERY_PREVIEW_LEN],
                "status": req.status,
                "created_at": req.created_at,
                "intent": profile.intent if profile else None,
                "complexity": profile.complexity if profile else None,
                "risk_severity": (profile.risk_vector or {}).get("severity") if profile else None,
                "model_action": route.model_action if route else None,
                "model_role": route.model_role if route else None,
                "selected_capabilities": (route.selected_capabilities or {}).get("values") if route else None,
                "verification_status": verification.status if verification else None,
                "intervened": req.id in intervened_requests,
            })
        return rows


def get_request_detail(request_id: str) -> dict | None:
    with session_scope() as session:
        req = session.get(RequestRecord, request_id)
        if req is None:
            return None

        trajectory = session.execute(
            select(TrajectoryRecord).where(TrajectoryRecord.request_id == request_id)
        ).scalar_one_or_none()
        trajectory_id = trajectory.id if trajectory else None

        steps = []
        events = []
        ledger_entries = []
        evaluations = []
        decisions = []
        interventions = []
        replans = []
        verifications = []
        if trajectory_id:
            steps = session.execute(
                select(TrajectoryStepRecord)
                .where(TrajectoryStepRecord.trajectory_id == trajectory_id)
                .order_by(TrajectoryStepRecord.sequence_number)
            ).scalars().all()
            events = session.execute(
                select(EventRecord)
                .where(EventRecord.trajectory_id == trajectory_id)
                .order_by(EventRecord.persisted_at)
            ).scalars().all()
            ledger_entries = session.execute(
                select(ExecutionLedgerRecord)
                .where(ExecutionLedgerRecord.trajectory_id == trajectory_id)
                .order_by(ExecutionLedgerRecord.sequence_number)
            ).scalars().all()
            evaluations = session.execute(
                select(ResponseEvaluationRecord)
                .where(ResponseEvaluationRecord.trajectory_id == trajectory_id)
            ).scalars().all()
            decisions = session.execute(
                select(DecisionRecord)
                .where(DecisionRecord.trajectory_id == trajectory_id)
                .order_by(DecisionRecord.attempt_number)
            ).scalars().all()
            interventions = session.execute(
                select(InterventionRecord)
                .where(InterventionRecord.trajectory_id == trajectory_id)
                .order_by(InterventionRecord.created_at)
            ).scalars().all()
            replans = session.execute(
                select(ReplanRecord)
                .where(ReplanRecord.trajectory_id == trajectory_id)
                .order_by(ReplanRecord.created_at)
            ).scalars().all()
            verifications = session.execute(
                select(VerificationRecord)
                .where(VerificationRecord.trajectory_id == trajectory_id)
            ).scalars().all()

        profile = session.execute(
            select(QueryProfileRecord)
            .where(QueryProfileRecord.request_id == request_id)
            .order_by(desc(QueryProfileRecord.created_at))
            .limit(1)
        ).scalar_one_or_none()
        route = session.execute(
            select(RouteDecisionRecord)
            .where(RouteDecisionRecord.request_id == request_id)
            .order_by(desc(RouteDecisionRecord.created_at))
            .limit(1)
        ).scalar_one_or_none()
        invocation = session.execute(
            select(ModelInvocationRecord)
            .where(ModelInvocationRecord.request_id == request_id)
            .order_by(desc(ModelInvocationRecord.started_at))
            .limit(1)
        ).scalar_one_or_none()

        # Permission Lineage (bootstrap SS25/SS33: USER -> AGENT -> PERMISSION
        # -> DATA -> TOOL -> DESTINATION -> ACTION) -- derived from the
        # AGENT capability node's own trajectory step, not a separate
        # table (same "derive, don't duplicate" reasoning as Trust above):
        # every field here is already recorded by
        # controlplane.capabilities.agent_capability.AgentCapability's
        # output, just not previously surfaced anywhere.
        permission_lineage = None
        agent_step = next((s for s in steps if s.step_type == "route:agent_action"), None)
        if agent_step is not None and agent_step.output_ref:
            out = agent_step.output_ref
            permission_lineage = {
                "requested_tool": out.get("proposed_tool"),
                "tool_call": out.get("tool_call"),
                "authorization": out.get("governance_action"),
                "authorization_reason": out.get("governance_reason"),
                "consequence_class": out.get("consequence_class"),
                "execution_status": out.get("execution_status"),
                "destination": (out.get("tool_result") or {}).get("destination"),
                "accessed_resource": (out.get("tool_result") or {}).get("path") or (out.get("tool_result") or {}).get("template"),
            }

        trust = None
        if decisions and verifications and profile and profile.risk_vector:
            try:
                last_decision = decisions[-1]
                trust_result = TrustEngine().assess(
                    verification=VerificationResult(
                        status=verifications[-1].status, reason=verifications[-1].reason,
                        checked_evaluators=verifications[-1].checked_evaluators or [],
                    ),
                    decision=ControlDecision(
                        action=last_decision.action, reason=last_decision.reason,
                        triggering_evaluator=last_decision.triggering_evaluator,
                        attempt_number=last_decision.attempt_number, can_retry=last_decision.can_retry,
                    ),
                    risk=RiskProfile(**profile.risk_vector),
                )
                trust = {"level": trust_result.level.value, "reason": trust_result.reason, "contributing_factors": trust_result.contributing_factors}
            except (TypeError, ValueError):
                # Trust is derived, not stored -- recomputed here from
                # already-persisted decision/verification/risk rows each
                # time the detail page is viewed (see docs/PROJECT_STATE/DECISIONS.md
                # for why no separate trust table exists). A malformed or
                # missing upstream field should degrade to "not shown,"
                # never a fabricated trust level.
                trust = None

        return {
            "request": {
                "id": req.id, "query_text": req.query_text, "status": req.status,
                "created_at": req.created_at, "completed_at": req.completed_at,
            },
            "trajectory": {
                "id": trajectory.id, "status": trajectory.status, "final_status": trajectory.final_status,
            } if trajectory else None,
            "query_profile": {
                "intent": profile.intent, "domain": profile.domain, "complexity": profile.complexity,
                "sensitivity": profile.sensitivity, "actionability": profile.actionability,
                "data_requirements": profile.data_requirements, "capability_hints": profile.capability_hints,
                "risk_vector": profile.risk_vector, "source": profile.source,
            } if profile else None,
            "route_decision": {
                "selected_capabilities": route.selected_capabilities, "restricted_capabilities": route.restricted_capabilities,
                "capability_reason": route.capability_reason, "execution_graph": route.execution_graph,
                "model_action": route.model_action, "model_role": route.model_role,
                "require_verification": route.require_verification, "human_approval_required": route.human_approval_required,
                "model_reason": route.model_reason,
                "expected_cost_class": route.expected_cost_class, "expected_latency_class": route.expected_latency_class,
            } if route else None,
            "answer": invocation.output_text if invocation else None,
            "model": {
                "provider": invocation.provider, "model": invocation.model, "status": invocation.status,
                "latency_ms": invocation.latency_ms, "input_tokens": invocation.input_tokens, "output_tokens": invocation.output_tokens,
            } if invocation else None,
            "trajectory_steps": [
                {
                    "sequence_number": s.sequence_number, "step_type": s.step_type, "status": s.status,
                    "input_ref": s.input_ref, "output_ref": s.output_ref,
                    "started_at": s.started_at, "completed_at": s.completed_at,
                } for s in steps
            ],
            "events": [
                {"event_type": e.event_type, "severity": e.severity, "payload": e.payload, "observed_at": e.observed_at}
                for e in events
            ],
            "ledger": [
                {
                    "action_type": l.action_type, "consequence_class": l.consequence_class,
                    "resource_id": l.resource_id, "metadata": l.metadata_, "occurred_at": l.occurred_at,
                } for l in ledger_entries
            ],
            "evaluations": [
                {"evaluator": ev.evaluator, "status": ev.status, "label": ev.label, "score": float(ev.score) if ev.score is not None else None, "result": ev.result}
                for ev in evaluations
            ],
            "decisions": [
                {
                    "attempt_number": d.attempt_number, "action": d.action, "reason": d.reason,
                    "triggering_evaluator": d.triggering_evaluator, "can_retry": d.can_retry,
                } for d in decisions
            ],
            "interventions": [
                {
                    "intervention_type": iv.intervention_type, "reason": iv.reason,
                    "expected_effect": iv.expected_effect, "actual_effect": iv.actual_effect,
                } for iv in interventions
            ],
            "replans": [
                {
                    "trigger": rp.trigger, "from_plan_version": rp.from_plan_version,
                    "to_plan_version": rp.to_plan_version, "reason": rp.reason,
                } for rp in replans
            ],
            "verification": (
                {"status": verifications[-1].status, "reason": verifications[-1].reason, "checked_evaluators": verifications[-1].checked_evaluators}
                if verifications else None
            ),
            "trust": trust,
            "permission_lineage": permission_lineage,
            # Component-level health + failure localization (Milestone 10).
            # Derived, like Trust and Permission Lineage above -- no new
            # table. Answers "WHICH component failed and why?", not just
            # "did the request fail?". See controlplane/diagnostics/.
            **_diagnostics_block(
                steps=steps, route=route, evaluations=evaluations,
                decisions=decisions, verifications=verifications,
                trust=trust, profile=profile, invocation=invocation,
            ),
        }


def _diagnostics_block(*, steps, route, evaluations, decisions, verifications,
                        trust, profile, invocation) -> dict:
    """Assemble the component health view. Isolated so a malformed row
    degrades to 'not shown' instead of breaking the whole detail page --
    the same defensive posture already used for Trust above."""
    try:
        step_dicts = [
            {"step_type": s.step_type, "status": s.status,
             "started_at": s.started_at, "completed_at": s.completed_at}
            for s in steps
        ]
        graph_nodes = ((route.execution_graph or {}).get("nodes") or []) if route else []
        evaluation_dicts = [
            {"evaluator": ev.evaluator, "status": ev.status, "label": ev.label,
             "recommended_signal": (ev.result or {}).get("recommended_signal")}
            for ev in evaluations
        ]
        last_decision = (
            {"action": decisions[-1].action, "reason": decisions[-1].reason,
             "triggering_evaluator": decisions[-1].triggering_evaluator,
             "attempt_number": decisions[-1].attempt_number,
             "requires_intervention": decisions[-1].action not in ("CONTINUE", "VERIFY")}
            if decisions else None
        )
        verification_dict = (
            {"status": verifications[-1].status, "reason": verifications[-1].reason}
            if verifications else None
        )
        model_meta = (
            {"provider": invocation.provider, "model": invocation.model,
             "role": (route.model_role if route else None), "latency_ms": invocation.latency_ms}
            if invocation else None
        )
        reports = build_component_reports(
            steps=step_dicts, graph_nodes=graph_nodes, evaluations=evaluation_dicts,
            decision=last_decision, verification=verification_dict, trust=trust,
            risk=(profile.risk_vector if profile else None),
            fingerprint=({"intent": profile.intent, "complexity": profile.complexity,
                          "capability_hints": profile.capability_hints} if profile else None),
            model_meta=model_meta,
        )
        failure = localize(
            steps=step_dicts, graph_nodes=graph_nodes, evaluations=evaluation_dicts,
            decision=last_decision, verification=verification_dict,
        )
        return {
            "component_health": [r.to_dict() for r in reports],
            "failure_localization": failure.to_dict(),
        }
    except (TypeError, ValueError, AttributeError, KeyError):
        return {"component_health": None, "failure_localization": None}


def aggregate_stats() -> dict:
    """Historical/aggregate view (bootstrap SS36) -- counts only, no PII,
    computed directly from the same tables, not a separate materialized
    analytics store (avoids adding infrastructure for this scale)."""
    from collections import Counter

    with session_scope() as session:
        requests = session.execute(select(RequestRecord)).scalars().all()
        profiles = session.execute(select(QueryProfileRecord)).scalars().all()
        routes = session.execute(select(RouteDecisionRecord)).scalars().all()
        decisions = session.execute(select(DecisionRecord)).scalars().all()
        interventions = session.execute(select(InterventionRecord)).scalars().all()
        verifications = session.execute(select(VerificationRecord)).scalars().all()

    status_counts = Counter(r.status for r in requests)
    risk_counts = Counter((p.risk_vector or {}).get("severity", "UNKNOWN") for p in profiles)
    action_counts = Counter(r.model_action for r in routes)
    role_counts = Counter(r.model_role for r in routes if r.model_role)
    decision_counts = Counter(d.action for d in decisions)
    intervention_counts = Counter(iv.intervention_type for iv in interventions)
    verification_counts = Counter(v.status for v in verifications)
    intervened_requests = {iv.request_id for iv in interventions}

    return {
        "total_requests": len(requests),
        "status_distribution": dict(status_counts),
        "risk_distribution": dict(risk_counts),
        "model_action_distribution": dict(action_counts),
        "model_role_distribution": dict(role_counts),
        "human_review_rate": f"{action_counts.get('HUMAN_REVIEW', 0)}/{len(routes)}" if routes else "0/0",
        "abstain_rate": f"{action_counts.get('ABSTAIN', 0)}/{len(routes)}" if routes else "0/0",
        "decision_distribution": dict(decision_counts),
        "intervention_distribution": dict(intervention_counts),
        "verification_distribution": dict(verification_counts),
        "intervention_rate": f"{len(intervened_requests)}/{len(requests)}" if requests else "0/0",
    }
