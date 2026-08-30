"""The multi-agent control view (§50, §52, §67).

The dashboard could already draw the agent topology and the messages
between agents. It could not answer the question a reviewer actually
asks, which is not "how many agents ran" but "which of them were worth
running".

This aggregates the per-request contribution records the runtime now
emits into the two judgements §67 asks for:

    per ROLE            USEFUL / REDUNDANT / UNCERTAIN, from how that
                        role's agents have actually scored across
                        requests, not from what the role is called
    per CHANNEL         whether handoffs changed anything on arrival

Read-only, and derived entirely from recorded events -- the view cannot
claim a handoff or a contribution that was never written down.

A NOTE ON HONESTY OF THE VERDICTS. A role is only called REDUNDANT when
its agents have run enough times to say so; below that threshold it is
UNCERTAIN, and the sample size is shown beside it. A dashboard that
declares a role useless on one observation is worse than one that says
nothing.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import desc, select

from controlplane.db.engine import session_scope
from controlplane.db.models import EventRecord

MIN_OBSERVATIONS_FOR_ROLE_VERDICT = 3
"""Below this, a role's verdict is UNCERTAIN however uniform its record
looks. One redundant run is an anecdote."""


def _contribution_events(limit: int) -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(EventRecord)
            .where(EventRecord.event_type == "AGENT_ACTION_GOVERNED")
            .order_by(desc(EventRecord.persisted_at))
            .limit(limit)
        ).scalars().all()
        return [
            {"request_id": r.request_id, "trajectory_id": r.trajectory_id,
             "observed_at": r.observed_at, "payload": dict(r.payload or {})}
            for r in rows
        ]


def _message_events(limit: int) -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(EventRecord)
            .where(EventRecord.event_type == "AGENT_MESSAGE_SENT")
            .order_by(desc(EventRecord.persisted_at))
            .limit(limit)
        ).scalars().all()
        return [
            {"request_id": r.request_id, "payload": dict(r.payload or {})}
            for r in rows
        ]


def _role_verdict(records: list[dict]) -> tuple[str, str]:
    """USEFUL / REDUNDANT / UNCERTAIN for one role, with its reason."""
    n = len(records)
    if n < MIN_OBSERVATIONS_FOR_ROLE_VERDICT:
        return "UNCERTAIN", f"only {n} observation(s); too few to judge a role"

    useful = sum(1 for r in records if r["verdict"] in ("ESSENTIAL", "CONTRIBUTING"))
    wasted = n - useful
    if useful == 0:
        return "REDUNDANT", f"none of {n} run(s) contributed unique information"
    if wasted / n >= 0.5:
        return "UNCERTAIN", f"{wasted} of {n} run(s) added nothing; the role pays off inconsistently"
    return "USEFUL", f"{useful} of {n} run(s) contributed unique information"


def build_agent_view(limit: int = 200) -> dict:
    """Aggregate agent behaviour across recent requests."""
    contribution_events = [
        e for e in _contribution_events(limit)
        if (e["payload"] or {}).get("scope") == "CONTRIBUTION"
    ]
    composition_events = [
        e for e in _contribution_events(limit)
        if (e["payload"] or {}).get("scope") == "COMPOSITION"
    ]
    messages = _message_events(limit)

    per_request: list[dict] = []
    by_role: dict[str, list[dict]] = defaultdict(list)
    verdict_counts: dict[str, int] = defaultdict(int)
    total_agents = wasted_agents = 0
    wasted_latency_ms = 0.0

    for event in contribution_events:
        payload = event["payload"]
        agents = payload.get("agents") or []
        per_request.append({
            "request_id": event["request_id"],
            "observed_at": event["observed_at"],
            "agent_count": payload.get("agent_count", len(agents)),
            "essential_count": payload.get("essential_count", 0),
            "redundant_count": payload.get("redundant_count", 0),
            "inert_count": payload.get("inert_count", 0),
            "wasted_agent_rate": payload.get("wasted_agent_rate", 0.0),
            "wasted_latency_ms": payload.get("wasted_latency_ms", 0.0),
            "agents": agents,
        })
        wasted_latency_ms += payload.get("wasted_latency_ms") or 0.0
        for agent in agents:
            total_agents += 1
            verdict = agent.get("verdict", "UNCERTAIN")
            verdict_counts[verdict] += 1
            if verdict in ("REDUNDANT", "INERT"):
                wasted_agents += 1
            by_role[agent.get("role") or "UNKNOWN"].append(agent)

    roles = []
    for role, records in sorted(by_role.items()):
        verdict, reason = _role_verdict(records)
        unique = sum(r.get("unique_evidence", 0) for r in records)
        duplicate = sum(r.get("duplicate_evidence", 0) for r in records)
        roles.append({
            "role": role,
            "observations": len(records),
            "verdict": verdict,
            "reason": reason,
            "unique_evidence": unique,
            "duplicate_evidence": duplicate,
            "information_gain": round(unique / (unique + duplicate), 3) if unique + duplicate else 0.0,
        })

    # §19: a channel is judged by what arrived and changed, not by volume.
    handoffs = [m for m in messages if (m["payload"] or {}).get("message_type") == "HANDOFF"]
    influence_counts: dict[str, int] = defaultdict(int)
    for event in contribution_events:
        for agent in event["payload"].get("agents") or []:
            influence_counts[agent.get("downstream_influence") or "NONE"] += 1
    changed = influence_counts["CHANGED_STEP_RISK"] + influence_counts["CHANGED_TOOL_OUTPUT"]
    delivered = changed + influence_counts["OBSERVED_ONLY"]

    return {
        "request_count": len(per_request),
        "total_agents": total_agents,
        "verdict_counts": dict(verdict_counts),
        "wasted_agent_rate": round(wasted_agents / total_agents, 3) if total_agents else None,
        "wasted_latency_ms": round(wasted_latency_ms, 1),
        "roles": roles,
        "per_request": per_request[:25],
        "communication": {
            "handoff_count": len(handoffs),
            "delivered_count": delivered,
            "changed_behaviour_count": changed,
            # The honest denominator: of the handoffs that reached an
            # agent, how many altered what it did. Volume is not utility.
            "utility_rate": round(changed / delivered, 3) if delivered else None,
            "sensitivity_breakdown": _sensitivity_breakdown(handoffs),
        },
        "composition_flags": [
            {"request_id": e["request_id"],
             "risk": e["payload"].get("risk"),
             "reason": e["payload"].get("reason"),
             "agent_chain": e["payload"].get("agent_chain") or []}
            for e in composition_events
            if e["payload"].get("risk") and e["payload"].get("risk") != "NONE"
        ][:25],
    }


def _sensitivity_breakdown(handoffs: list[dict]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    for message in handoffs:
        counts[(message["payload"] or {}).get("data_sensitivity") or "UNKNOWN"] += 1
    return dict(counts)
