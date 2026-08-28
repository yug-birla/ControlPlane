"""Assemble a per-request component health report from persisted data.

Answers the Milestone 10 core product question (§77): for a given
request, what did each component do, what did it conclude, how long did
it take, and -- if the outcome was bad -- WHICH component is responsible?

No new storage. Everything here is read back from rows the runtime
already writes: ``trajectory_steps``, ``response_evaluations``,
``decisions``, ``verifications``, ``model_invocations``, and the
``route_decisions`` graph snapshot. See
``controlplane/diagnostics/component_state.py`` for why this is derived
rather than duplicated.
"""

from __future__ import annotations

from controlplane.diagnostics.component_state import (
    Attribution,
    Component,
    ComponentReport,
    ComponentStatus,
    FailureLocalization,
    localize_failure,
)

# Trajectory step_type -> the component it represents. Steps not listed
# here (e.g. "received", "completed") are runtime bookkeeping, not
# components, and are excluded from the component view rather than
# reported as mystery entries.
_STEP_COMPONENTS: dict[str, Component] = {
    "query_profiling": Component.QUERY_PROFILER,
    "risk_assessment": Component.RISK_PROFILER,
    "routing": Component.CAPABILITY_ROUTER,
    "evaluation": Component.EVALUATION,
    "generation": Component.GENERATION,
    "model_invocation": Component.GENERATION,
}

_STATUS_MAP = {
    "COMPLETED": ComponentStatus.COMPLETED,
    "FAILED": ComponentStatus.FAILED,
    "SKIPPED": ComponentStatus.SKIPPED,
    "BLOCKED": ComponentStatus.BLOCKED,
    "RUNNING": ComponentStatus.RUNNING,
    "PENDING": ComponentStatus.NOT_STARTED,
}


def _status(raw: str | None) -> ComponentStatus:
    return _STATUS_MAP.get((raw or "").upper(), ComponentStatus.NOT_STARTED)


def _as_list(value) -> list:
    """List-valued profile fields are persisted as ``{"values": [...]}``
    (see RouteDecisionRecord/QueryProfileRecord), but arrive as plain
    lists from in-memory fingerprints. Handle both -- reading the dict
    as a sequence yielded its KEYS, which surfaced in the dashboard as
    the literal signal "values"."""
    if isinstance(value, dict):
        return list(value.get("values") or [])
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _latency_ms(step: dict) -> int | None:
    started, completed = step.get("started_at"), step.get("completed_at")
    if not started or not completed:
        return None
    try:
        return int((completed - started).total_seconds() * 1000)
    except (TypeError, AttributeError):
        return None


def _node_component(node: dict) -> Component:
    capability = (node.get("capability") or "").upper()
    return {
        "RAG": Component.RETRIEVAL,
        "SQL": Component.SQL,
        "AGENT": Component.AGENT,
        "GENERAL": Component.GENERATION,
    }.get(capability, Component.GENERATION)


def build_component_reports(
    *,
    steps: list[dict],
    graph_nodes: list[dict],
    evaluations: list[dict],
    decision: dict | None,
    verification: dict | None,
    trust: dict | None,
    risk: dict | None,
    fingerprint: dict | None,
    model_meta: dict | None,
) -> list[ComponentReport]:
    reports: list[ComponentReport] = []
    by_component: dict[Component, dict] = {}
    for step in steps:
        component = _STEP_COMPONENTS.get(step.get("step_type", ""))
        if component and component not in by_component:
            by_component[component] = step

    # --- Understanding / assessment / planning ---
    if Component.QUERY_PROFILER in by_component:
        step = by_component[Component.QUERY_PROFILER]
        hints = _as_list((fingerprint or {}).get("capability_hints"))
        reports.append(ComponentReport(
            component=Component.QUERY_PROFILER,
            status=_status(step.get("status")),
            summary=f"intent={(fingerprint or {}).get('intent')}, "
                    f"complexity={(fingerprint or {}).get('complexity')}",
            signal="+".join(str(h) for h in hints) or None,
            latency_ms=_latency_ms(step),
            decision_impact="selected the capabilities the router could choose from",
        ))

    if Component.RISK_PROFILER in by_component:
        step = by_component[Component.RISK_PROFILER]
        severity = (risk or {}).get("severity")
        reports.append(ComponentReport(
            component=Component.RISK_PROFILER,
            status=_status(step.get("status")),
            summary=f"severity={severity}",
            signal=severity,
            latency_ms=_latency_ms(step),
            decision_impact="set the policy tier and control depth" if severity else None,
        ))

    if Component.CAPABILITY_ROUTER in by_component:
        step = by_component[Component.CAPABILITY_ROUTER]
        caps = [n.get("capability") for n in graph_nodes]
        reports.append(ComponentReport(
            component=Component.CAPABILITY_ROUTER,
            status=_status(step.get("status")),
            summary=f"{len(graph_nodes)} node(s): {', '.join(c for c in caps if c)}",
            signal="+".join(sorted({c for c in caps if c})) or None,
            latency_ms=_latency_ms(step),
            decision_impact="determined which capabilities could contribute evidence",
        ))

    # --- Capability nodes, from the persisted graph snapshot ---
    for node in graph_nodes:
        component = _node_component(node)
        if component is Component.GENERATION:
            continue  # reported once below, with real model metadata
        reports.append(ComponentReport(
            component=component,
            status=_status(node.get("status")),
            summary=f"node {node.get('node_id')}",
            latency_ms=node.get("latency_ms"),
            decision_impact="supplied evidence to the generation prompt"
            if _status(node.get("status")) is ComponentStatus.COMPLETED else None,
        ))

    # --- Generation ---
    if model_meta:
        reports.append(ComponentReport(
            component=Component.GENERATION,
            status=ComponentStatus.COMPLETED,
            summary=f"{model_meta.get('provider')}/{model_meta.get('model')} "
                    f"role={model_meta.get('role')}",
            signal=model_meta.get("role"),
            latency_ms=model_meta.get("latency_ms"),
        ))

    # --- Evaluation: one line per evaluator, so a flagged evaluator is
    #     visible rather than collapsed into a single pass/fail. ---
    for evaluation in evaluations:
        signal = evaluation.get("recommended_signal")
        status = (
            ComponentStatus.DEGRADED
            if signal in ("FLAG_FOR_REVIEW", "BLOCK")
            else ComponentStatus.COMPLETED
        )
        if evaluation.get("status") == "NOT_IMPLEMENTED":
            status = ComponentStatus.SKIPPED
        reports.append(ComponentReport(
            component=Component.EVALUATION,
            status=status,
            summary=f"{evaluation.get('evaluator')}={evaluation.get('label')}",
            signal=signal,
            decision_impact="triggered the control decision"
            if decision and decision.get("triggering_evaluator") == evaluation.get("evaluator")
            else None,
        ))

    if decision:
        reports.append(ComponentReport(
            component=Component.DECISION,
            status=ComponentStatus.COMPLETED,
            summary=decision.get("reason", ""),
            signal=decision.get("action"),
            decision_impact=f"attempt {decision.get('attempt_number')}; "
                            f"intervention={'yes' if decision.get('requires_intervention') else 'no'}",
        ))

    if verification:
        status = (
            ComponentStatus.DEGRADED
            if verification.get("status") in ("REJECTED", "NOT_VERIFIED")
            else ComponentStatus.COMPLETED
        )
        reports.append(ComponentReport(
            component=Component.VERIFICATION,
            status=status,
            summary=verification.get("reason", ""),
            signal=verification.get("status"),
        ))

    if trust:
        reports.append(ComponentReport(
            component=Component.TRUST,
            status=ComponentStatus.COMPLETED,
            summary=trust.get("reason", ""),
            signal=trust.get("level"),
        ))

    return reports


def localize(
    *,
    steps: list[dict],
    graph_nodes: list[dict],
    evaluations: list[dict],
    decision: dict | None,
    verification: dict | None,
) -> FailureLocalization:
    """Answer 'where did this request go wrong?'"""
    failed_steps = [
        s.get("step_type", "") for s in steps if (s.get("status") or "").upper() == "FAILED"
    ]
    retrieval_nodes = [
        n for n in graph_nodes if (n.get("capability") or "").upper() in ("RAG", "SQL")
    ]
    retrieval_ran = any(
        (n.get("status") or "").upper() == "COMPLETED" for n in retrieval_nodes
    )
    # Evidence count is approximated by completed evidence-producing
    # nodes: the per-node payload is not retained on the graph snapshot.
    # Stated rather than silently treated as an exact chunk count.
    evidence_count = sum(
        1 for n in retrieval_nodes if (n.get("status") or "").upper() == "COMPLETED"
    )
    return localize_failure(
        evaluations=evaluations,
        decision=decision,
        verification=verification,
        retrieval_ran=retrieval_ran,
        evidence_count=evidence_count,
        failed_steps=failed_steps,
    )


__all__ = [
    "Attribution",
    "Component",
    "ComponentReport",
    "ComponentStatus",
    "FailureLocalization",
    "build_component_reports",
    "localize",
]
