"""The Live Execution Console: one request, told as a governed trajectory.

The existing detail page is a set of panels. It answers "what did each
component record" and does not answer the question the product is
actually about: **what did ControlPlane decide, and why did the execution
change**.

This assembles the governance spine --

    QUERY -> UNDERSTANDING -> RISK -> POLICY -> CAPABILITIES -> PLAN
    -> EXECUTION -> EVALUATION -> DECISION -> INTERVENTION/REPLAN
    -> VERIFICATION -> TRUST -> OUTPUT

-- from data ``get_request_detail`` has already fetched. No new queries,
no second state model, and no event infrastructure of its own.

WHAT IT WILL NOT DO. Every stage is derived from a recorded value or
marked ``NOT RECORDED``. A stage that did not happen for this request --
no replan, no intervention -- says so rather than rendering an empty box
that reads like a stage that passed. A null latency stays null; the
project has already shipped one metric that turned an absent measurement
into a confident ``0``.
"""

from __future__ import annotations

from datetime import datetime

# Stages that exist for every request, in governance order. The pipeline
# is fixed because the control loop is fixed; what varies is which
# stages fired and what they recorded.
_STAGE_ORDER = [
    ("query", "Query Received"),
    ("understanding", "Query Intelligence"),
    ("risk", "Risk"),
    ("policy", "Policy"),
    ("capabilities", "Capability Discovery"),
    ("plan", "Plan"),
    ("execution", "Execution"),
    ("evaluation", "Evaluation"),
    ("decision", "Decision"),
    ("intervention", "Intervention / Replan"),
    ("verification", "Verification"),
    ("trust", "Trust"),
    ("output", "Output"),
]

_OK = "COMPLETED"
_WARN = "WARNING"
_FAIL = "FAILED"
_SKIP = "NOT_TRIGGERED"
_MISSING = "NOT_RECORDED"


def _row(label, value, *, note=None):
    return {"label": label, "value": value, "note": note}


def _parse(ts):
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def build_console(detail: dict) -> dict:
    """One request as a governed trajectory."""
    if not detail:
        return {"available": False}

    request = detail.get("request") or {}
    profile = detail.get("query_profile") or {}
    route = detail.get("route_decision") or {}
    graph = route.get("execution_graph") or {}
    nodes = graph.get("nodes") or []
    evaluations = detail.get("evaluations") or []
    decisions = detail.get("decisions") or []
    replans = detail.get("replans") or []
    interventions = detail.get("interventions") or []
    verification = detail.get("verification") or {}
    trust = detail.get("trust") or {}
    model = detail.get("model") or {}
    events = detail.get("events") or []

    stages: dict[str, dict] = {}

    stages["query"] = {
        "status": _OK,
        "summary": request.get("query_text") or "--",
        "rows": [
            _row("request", request.get("id")),
            _row("status", request.get("status")),
        ],
    }

    risk_vector = profile.get("risk_vector") or {}
    stages["understanding"] = {
        "status": _OK if profile else _MISSING,
        "summary": f"{profile.get('intent') or '--'} &middot; {profile.get('complexity') or '--'} complexity",
        "rows": [
            _row("intent", profile.get("intent")),
            _row("domain", profile.get("domain")),
            _row("complexity", profile.get("complexity")),
            _row("sensitivity", profile.get("sensitivity")),
            _row("actionability", profile.get("actionability")),
            _row("data requirements", ", ".join(profile.get("data_requirements") or []) or "--"),
            _row("capability hints", ", ".join(profile.get("capability_hints") or []) or "--"),
            _row("produced by", profile.get("source"),
                 note="which profiler layer resolved these fields"),
        ],
    }

    severity = risk_vector.get("severity") if isinstance(risk_vector, dict) else None
    dimensions = []
    if isinstance(risk_vector, dict):
        for key, value in risk_vector.items():
            if key in ("severity", "reason", "categories"):
                continue
            dimensions.append(_row(key, value))
    stages["risk"] = {
        "status": _WARN if severity in ("HIGH_RISK", "CRITICAL") else (_OK if severity else _MISSING),
        "summary": severity or "not recorded",
        "rows": dimensions or [_row("detail", "no per-dimension risk recorded for this request")],
    }

    stages["policy"] = {
        "status": _OK if route else _MISSING,
        "summary": ("human approval required" if route.get("human_approval_required")
                    else "no human approval required"),
        "rows": [
            _row("human approval required", route.get("human_approval_required")),
            _row("verification required", route.get("require_verification")),
            _row("expected cost class", route.get("expected_cost_class")),
            _row("expected latency class", route.get("expected_latency_class")),
        ],
    }

    stages["capabilities"] = {
        "status": _OK if route.get("capability_reason") else _MISSING,
        "summary": route.get("capability_reason") or "--",
        "rows": [_row("selection", route.get("capability_reason"),
                      note="which hints survived policy, and why")],
    }

    agent_nodes = [n for n in nodes if n.get("capability") == "AGENT"]
    independent = [n for n in nodes if not n.get("depends_on")]
    stages["plan"] = {
        "status": _OK if nodes else _MISSING,
        "summary": f"{len(nodes)} node(s), {len(agent_nodes)} agent(s)",
        "rows": [
            _row("nodes", ", ".join(n.get("node_id") for n in nodes) or "--"),
            _row("parallel group", ", ".join(n.get("node_id") for n in independent)
                 if len(independent) > 1 else "none",
                 note="nodes with no dependencies -- the scheduler ran these concurrently"),
            _row("plan versions", len(replans) + 1),
        ],
    }

    failed_nodes = [n for n in nodes if n.get("status") == "FAILED"]
    stages["execution"] = {
        "status": _FAIL if failed_nodes else (_OK if nodes else _MISSING),
        "summary": (f"{len(failed_nodes)} node(s) failed" if failed_nodes
                    else f"{len(nodes)} node(s) completed"),
        "rows": [
            _row(n.get("node_id"),
                 f"{n.get('status')} &middot; "
                 + (f"{n.get('latency_ms'):.0f} ms" if n.get("latency_ms") is not None else "latency not recorded"),
                 note=n.get("error"))
            for n in nodes
        ],
    }

    concerns = [e for e in evaluations
                if (e.get("result") or {}).get("recommended_signal") in ("FLAG_FOR_REVIEW", "BLOCK")]
    stages["evaluation"] = {
        "status": _WARN if concerns else (_OK if evaluations else _MISSING),
        "summary": f"{len(evaluations)} evaluator(s), {len(concerns)} raised a concern",
        "rows": [
            _row(e.get("evaluator"), e.get("label") or e.get("status"),
                 note=(e.get("result") or {}).get("rationale"))
            for e in evaluations
        ],
    }

    decision = decisions[0] if decisions else None
    stages["decision"] = {
        "status": _WARN if decision and decision.get("action") in (
            "HUMAN_REVIEW", "ABSTAIN", "BLOCK") else (_OK if decision else _MISSING),
        "summary": (decision or {}).get("action") or "not recorded",
        "rows": [
            _row("action", (decision or {}).get("action")),
            _row("triggering evaluator", (decision or {}).get("triggering_evaluator")),
            _row("reason", (decision or {}).get("reason")),
            _row("attempt", (decision or {}).get("attempt_number")),
        ] if decision else [_row("detail", "no decision recorded")],
    }

    if replans or interventions:
        stages["intervention"] = {
            "status": _WARN,
            "summary": f"{len(interventions)} intervention(s), {len(replans)} replan(s)",
            "rows": (
                [_row("intervention", i.get("action") or i.get("intervention_type"),
                      note=i.get("reason")) for i in interventions]
                + [_row(f"plan v{r.get('new_plan_version')}", r.get("trigger"),
                        note=r.get("reason")) for r in replans]
            ),
        }
    else:
        stages["intervention"] = {
            "status": _SKIP,
            "summary": "no intervention and no replan for this request",
            "rows": [_row("detail",
                          "the plan executed as created -- this stage exists and did not fire, "
                          "which is different from not being implemented")],
        }

    stages["verification"] = {
        "status": (_FAIL if verification.get("status") == "REJECTED"
                   else _WARN if verification.get("status") in ("NOT_VERIFIED", "PARTIALLY_VERIFIED")
                   else _OK if verification else _MISSING),
        "summary": verification.get("status") or "not recorded",
        "rows": [
            _row("status", verification.get("status")),
            _row("reason", verification.get("reason")),
            _row("checked", ", ".join(verification.get("checked_evaluators") or []) or "--"),
        ],
    }

    stages["trust"] = {
        "status": (_OK if trust.get("level") == "HIGH"
                   else _WARN if trust.get("level") else _MISSING),
        "summary": trust.get("level") or "not recorded",
        "rows": [
            _row("level", trust.get("level")),
            _row("reason", trust.get("reason")),
            _row("derived from", "; ".join(trust.get("contributing_factors") or []) or "--",
                 note="computed from the stored decision/verification/risk records, not itself persisted"),
        ],
    }

    stages["output"] = {
        "status": _OK if detail.get("answer") else _WARN,
        "summary": (str(detail.get("answer"))[:160] + "...") if detail.get("answer") else "no answer released",
        "rows": [
            _row("model", f"{model.get('model') or '--'} ({model.get('provider') or '--'})"),
            _row("role", route.get("model_role")),
            _row("routing action", route.get("model_action")),
            _row("routing reason", route.get("model_reason")),
            _row("tokens", f"{model.get('input_tokens')} in / {model.get('output_tokens')} out"
                 if model.get("input_tokens") is not None else "not recorded"),
            _row("model latency",
                 f"{model.get('latency_ms'):.0f} ms" if model.get("latency_ms") is not None
                 else "not recorded"),
        ],
    }

    ordered = [{"key": key, "label": label, **stages[key]} for key, label in _STAGE_ORDER]

    # Replay: the recorded event stream, with elapsed offsets. Stepping
    # through this is a replay of what happened, never a simulation of
    # what might have.
    timestamps = [_parse(e.get("observed_at")) for e in events]
    first = next((t for t in timestamps if t), None)
    timeline = []
    for event, when in zip(events, timestamps):
        timeline.append({
            "event_type": event.get("event_type"),
            "severity": event.get("severity"),
            "observed_at": event.get("observed_at"),
            "offset_ms": int((when - first).total_seconds() * 1000) if (when and first) else None,
            "stage": _EVENT_STAGE.get(event.get("event_type")),
        })

    return {
        "available": True,
        "request_id": request.get("id"),
        "trajectory_id": (detail.get("trajectory") or {}).get("id"),
        "query": request.get("query_text"),
        "final_status": (detail.get("trajectory") or {}).get("final_status") or request.get("status"),
        "stages": ordered,
        "timeline": timeline,
        "event_count": len(events),
        "failure_localization": detail.get("failure_localization"),
    }


# Which governance stage an event belongs to, so replay can light up the
# spine as the recorded stream advances. Unknown event types map to None
# and are shown in the feed without moving the pipeline -- an unexpected
# event must never corrupt the view.
_EVENT_STAGE = {
    "QUERY_RECEIVED": "query",
    "QUERY_PROFILED": "understanding",
    "RISK_DETECTED": "risk",
    "PLAN_CREATED": "plan",
    "ROUTE_STARTED": "execution",
    "ROUTE_COMPLETED": "execution",
    "CAPABILITY_INVOKED_VIA_MCP": "execution",
    "AGENT_MESSAGE_SENT": "execution",
    "AGENT_ACTION_GOVERNED": "execution",
    "MODEL_CALLED": "output",
    "MODEL_FAILURE": "execution",
    "EVALUATION_COMPLETED": "evaluation",
    "HUMAN_REVIEW_REQUIRED": "decision",
    "INTERVENTION_APPLIED": "intervention",
    "PLAN_REVISED": "intervention",
    "VERIFICATION_PASSED": "verification",
    "VERIFICATION_FAILED": "verification",
    "FINAL_RESPONSE_GENERATED": "output",
}
