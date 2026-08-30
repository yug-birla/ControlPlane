"""Does removing the communication channel change what the system DOES?

WHY THIS EXPERIMENT EXISTS SEPARATELY. The previous communication
ablation was invalid: handoffs were synthesized after every agent had
already run, so suppressing the bus removed a log entry and nothing
else, and the two arms were identical by construction. That has been
fixed -- the bus is now the delivery channel -- and the fix has to be
measured rather than asserted.

It is measured HERE, apart from the quality benchmark, because the
effect of communication on GOVERNANCE is deterministic and needs no
generation model. When an actor is handed CONFIDENTIAL evidence its
external send moves from MEDIUM_RISK to HIGH_RISK, which moves the gate
from RESTRICT to HUMAN_REVIEW. That is a decision, not a sampled answer:
it is reproducible, it does not depend on decoding, and it can be run on
embedding models alone while a heavy job holds the RAM.

WHAT THIS DOES NOT MEASURE. Answer quality. Whether communication
improves what the user finally reads needs the generation model and is
left to the quality ablation. Reporting a governance effect as though it
were a quality effect would repeat the error this experiment exists to
correct, so the two are never combined into one number.

THE ARMS.

  WITH_COMMUNICATION      the shipped runtime: gatherer results are sent
                          through AgentBus and the actor reads its inbox
  WITHOUT_COMMUNICATION   an AgentBus that delivers nothing. The evidence
                          still exists upstream and the actor still runs;
                          it simply never receives it

CHANNEL INTEGRITY IS CHECKED BEFORE ANY SCORE IS REPORTED. The arms must
demonstrably differ in runtime state -- at least one case where the
communication arm built a handoff context and the suppressed arm did
not. If that check fails the experiment REFUSES to report, because a
null result from an ablation that did not ablate anything is exactly
what happened last time.

Run (CPU, embeddings only -- no generation, safe alongside a heavy job):
    .venv/Scripts/python -m controlplane.experiments.evaluate_agent_communication
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import date
from pathlib import Path

from controlplane.context import RequestContext
from controlplane.execution.graph import NodeStatus
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.governance.agent_bus import AgentBus
from controlplane.policy.baseline import PolicyBaseline
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.routing.capability_router import CapabilityRouter

DATASET_ID = "agent_collaboration_cases"
DATASET_VERSION = "v1"
_DATASET = Path("data/raw/generated/agent_collaboration_cases.json")

ARMS = ("WITH_COMMUNICATION", "WITHOUT_COMMUNICATION")


class _SilentBus:
    """Delivers nothing. Not a stub that breaks execution -- it satisfies
    the same interface so the actor still runs; it simply never receives
    what the gatherers found."""

    def __init__(self) -> None:
        self.messages: list = []

    def send(self, message):
        return message

    def messages_for(self, agent_id: str) -> list:
        return []

    def clear(self) -> None:
        return None


def _load() -> list[dict]:
    with open(_DATASET, encoding="utf-8-sig") as f:
        return json.load(f)


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _build_runtime(arm: str):
    """A Runtime with the real agent path and no generation model.

    ``object.__new__`` skips ``__init__`` deliberately: this experiment
    drives the agent subsystem, and loading a 1.5B generation model to
    measure a governance decision that does not consult one would be
    both slow and a RAM hazard next to the judge run.
    """
    from controlplane.capabilities.agent_capability import AgentCapability
    from controlplane.capabilities.rag_capability import RAGCapability
    from controlplane.capabilities.sql_capability import SQLCapability
    from controlplane.governance.multi_agent import CompositionGovernor
    from controlplane.mcp.client import MCPClient
    from controlplane.runtime import Runtime

    runtime = object.__new__(Runtime)
    runtime._agent_bus = AgentBus() if arm == "WITH_COMMUNICATION" else _SilentBus()
    runtime._agent_capability = AgentCapability()
    # THE HANDLERS MUST BE WIRED THE WAY THE RUNTIME WIRES THEM.
    #
    # A bare MCPClient() has none, and every capability call then returns
    # "registered but no handler is wired in this deployment". The
    # gatherers still reported COMPLETED, produced no evidence, and no
    # handoff was possible in EITHER arm -- so the ablation compared two
    # arms in which nothing had happened. Caught only by the
    # channel-integrity precondition, which is the entire reason it runs
    # before any score is reported.
    runtime._rag_capability = RAGCapability()
    runtime._sql_capability = SQLCapability()
    runtime._mcp_client = MCPClient(handlers={
        "RAG": lambda q, **kw: runtime._rag_capability.execute(q, **kw),
        "SQL": lambda q, **kw: runtime._sql_capability.execute(q, **kw),
        "AGENT": lambda q, **kw: runtime._agent_capability.execute(q),
    })
    runtime._composition_governor = CompositionGovernor()
    runtime._composition_assessment = None
    runtime._agent_contributions = []
    runtime._agent_conflicts = []
    runtime._publish = lambda *a, **kw: None
    return runtime


def _execute_agents(runtime, ctx, graph, query: str) -> dict:
    """Run the AGENT nodes in dependency order.

    Dependency order matters and is not cosmetic: an actor must run after
    its gatherers or there is nothing in ``output_ref`` to hand over, and
    the handoff would be empty for a reason that has nothing to do with
    the arm under test.
    """
    agent_nodes = [n for n in graph.nodes if n.capability == "AGENT"]
    remaining = list(agent_nodes)
    executed: list[str] = []

    def _mcp_invoke(_ctx, capability_id, q):
        """The Runtime's own path, minus event publication.

        Deliberately delegates to ``runtime._mcp_client`` rather than
        building a client here: a second client is a second wiring, and
        the first one silently had no handlers at all.
        """
        result = runtime._mcp_client.invoke(capability_id, q)
        if not result.ok:
            return {"status": "FAILED", "error": result.error}
        return {**result.output, "mcp": result.to_dict()}

    runtime._invoke_via_mcp = _mcp_invoke

    guard = 0
    while remaining and guard < 20:
        guard += 1
        for node in list(remaining):
            unmet = [d for d in node.depends_on
                     if any(n.node_id == d for n in agent_nodes) and d not in executed]
            if unmet:
                continue
            # latency_ms is a computed property; the executor times a node
            # by stamping started_at/completed_at, and this does the same so
            # the number means the same thing in both places.
            node.started_at = time.monotonic()
            try:
                node.output_ref = runtime._execute_agent_node(ctx, node, query, graph)
                node.status = NodeStatus.COMPLETED
            except Exception as exc:
                node.output_ref = {"error": f"{type(exc).__name__}: {exc}"}
                node.status = NodeStatus.FAILED
            node.completed_at = time.monotonic()
            executed.append(node.node_id)
            remaining.remove(node)

    return {n.node_id: n.output_ref for n in agent_nodes if n.output_ref}


def _gatherer_evidence_totals(graph) -> dict:
    """How much evidence the gatherers actually produced.

    Reported per case so "no handoff" can be told apart from "nothing to
    hand over" -- the distinction the first run of this experiment could
    not make.
    """
    from controlplane.governance.handoff import evidence_items

    totals = {}
    for node in graph.nodes:
        if node.capability != "AGENT" or not node.output_ref:
            continue
        if not (node.input_ref or {}).get("serves_capability"):
            continue
        totals[node.node_id] = len(evidence_items(node.output_ref))
    return totals


def _run_case(arm: str, case: dict) -> dict:
    profiler, risk_profiler, policy = HybridQueryProfiler(), BaselineRiskProfiler(), PolicyBaseline()
    router = CapabilityRouter()

    query = case["query"]
    fingerprint = profiler.profile(query)
    risk = risk_profiler.profile(query, fingerprint)
    decision = policy.decide(risk.severity)
    route = router.route(fingerprint, risk, decision)

    runtime = _build_runtime(arm)
    ctx = RequestContext.new()
    started = time.monotonic()
    with ctx.bind():
        results = _execute_agents(runtime, ctx, route.graph, query)
    latency_ms = (time.monotonic() - started) * 1000

    agent_nodes = [n for n in route.graph.nodes if n.capability == "AGENT"]
    roles = sorted((n.input_ref or {}).get("role") for n in agent_nodes if (n.input_ref or {}).get("role"))

    actor = next(
        (r for r in results.values()
         if r.get("agent_role") == "NOTIFIER" or r.get("proposed_tool") in
         ("send_notification", "write_report")),
        None,
    )
    received = actor.get("handoff_received") if actor else None

    # BOTH ARMS ARE SCORED AGAINST THE SAME EXPECTATION.
    #
    # The first version scored each arm against its own expected outcome,
    # which made both arms trivially 1.000 and hid the very effect the
    # experiment exists to measure: the CORRECT governance action for a
    # request does not depend on which arm produced it. The
    # without-communication expectation is retained below purely as a
    # mechanism check -- it says what the suppressed arm should do, not
    # what would be right.
    expected_action = case.get("expected_governance_action")
    mechanism_expectation = case.get("expected_governance_action_without_communication")

    return {
        "case_id": case["case_id"],
        "collaboration_class": case["collaboration_class"],
        "communication_class": case["communication_class"],
        "known_failing": bool(case.get("known_failing")),
        "agent_count": len(agent_nodes),
        "expected_agent_count": case["expected_agent_count"],
        "agent_count_matches": len(agent_nodes) == case["expected_agent_count"],
        "roles": roles,
        "expected_roles": sorted(case.get("expected_roles") or []),
        "roles_match": roles == sorted(case.get("expected_roles") or []),
        # The state that distinguishes the arms, recorded per case so the
        # integrity check is evidence rather than an assumption.
        "handoff_delivered": received is not None,
        "handoff_sensitivity": (received or {}).get("max_sensitivity"),
        "handoff_influence": actor.get("handoff_influence") if actor else None,
        "governance_action": actor.get("governance_action") if actor else None,
        "expected_governance_action": expected_action,
        "mechanism_expectation_without_communication": mechanism_expectation,
        "matches_mechanism_expectation": (
            actor.get("governance_action") == mechanism_expectation
            if actor and mechanism_expectation and arm == "WITHOUT_COMMUNICATION" else None
        ),
        "governance_action_correct": (
            actor.get("governance_action") == expected_action
            if actor and expected_action else None
        ),
        "step_risk": actor.get("step_risk") if actor else None,
        "message_count": len(getattr(runtime._agent_bus, "messages", [])),
        "gatherer_evidence": _gatherer_evidence_totals(route.graph),
        "latency_ms": latency_ms,
    }


def _channel_integrity(rows_with: list[dict], rows_without: list[dict]) -> dict:
    """Did the ablation actually ablate anything?

    Checked before any score is reported. A null result from an ablation
    that removed nothing is precisely the failure this experiment was
    written to correct.
    """
    delivered_with = [r["case_id"] for r in rows_with if r["handoff_delivered"]]
    delivered_without = [r["case_id"] for r in rows_without if r["handoff_delivered"]]
    return {
        "cases_with_delivery_in_communication_arm": delivered_with,
        "cases_with_delivery_in_suppressed_arm": delivered_without,
        "channel_actually_removed": bool(delivered_with) and not delivered_without,
        "reason": (
            f"{len(delivered_with)} case(s) built a handoff context with the bus enabled and "
            f"{len(delivered_without)} with it suppressed"
        ),
    }


def _aggregate(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["governance_action_correct"] is not None]
    plannable = [r for r in rows if not r["known_failing"]]
    n = len(rows) or 1
    return {
        "sample_count": len(rows),
        "governance_scored_count": len(scored),
        "governance_action_accuracy": (
            sum(1 for r in scored if r["governance_action_correct"]) / len(scored)
            if scored else None
        ),
        "plan_shape_accuracy": (
            sum(1 for r in plannable if r["agent_count_matches"]) / len(plannable)
            if plannable else None
        ),
        "plan_role_accuracy": (
            sum(1 for r in plannable if r["roles_match"]) / len(plannable)
            if plannable else None
        ),
        "handoff_delivered_count": sum(1 for r in rows if r["handoff_delivered"]),
        "handoff_changed_behaviour_count": sum(
            1 for r in rows if r["handoff_influence"] in ("CHANGED_STEP_RISK", "CHANGED_TOOL_OUTPUT")
        ),
        "total_messages": sum(r["message_count"] for r in rows),
        "latency_ms_mean": sum(r["latency_ms"] for r in rows) / n,
    }


def main() -> None:
    cases = _load()
    commit = _git_commit()
    print(f"{len(cases)} collaboration cases | git {commit}\n")

    experiment_id = record_experiment(
        experiment_name="agent_communication_ablation",
        component="multi_agent",
        algorithm="bus_as_channel_vs_suppressed",
        algorithm_version="v1",
    )

    all_rows: dict[str, list[dict]] = {}
    for arm in ARMS:
        print(f"=== {arm} ===")
        rows = []
        for i, case in enumerate(cases, 1):
            row = _run_case(arm, case)
            rows.append(row)
            mark = "OK" if row["governance_action_correct"] else (
                "--" if row["governance_action_correct"] is None else "MISS")
            print(f"  [{i:>2}/{len(cases)}] {row['case_id']} agents={row['agent_count']} "
                  f"handoff={'Y' if row['handoff_delivered'] else 'n'} "
                  f"gov={row['governance_action'] or '-':<13} {mark}")
        all_rows[arm] = rows
        print()

    integrity = _channel_integrity(all_rows["WITH_COMMUNICATION"], all_rows["WITHOUT_COMMUNICATION"])
    print("=" * 78)
    print("CHANNEL INTEGRITY")
    print("=" * 78)
    print(f"  {integrity['reason']}")
    print(f"  channel actually removed: {integrity['channel_actually_removed']}")
    if not integrity["channel_actually_removed"]:
        print("\nREFUSING TO REPORT. The suppressed arm is not distinguishable from the "
              "communication arm in runtime state, so any comparison between them would "
              "repeat the invalid ablation this experiment exists to correct.")
        return

    results = {arm: _aggregate(all_rows[arm]) for arm in ARMS}

    print("\n" + "=" * 78)
    print(f"{'METRIC':<38}{'WITH_COMMS':>20}{'WITHOUT_COMMS':>20}")
    print("=" * 78)
    for metric in ("governance_action_accuracy", "handoff_delivered_count",
                   "handoff_changed_behaviour_count", "plan_shape_accuracy",
                   "plan_role_accuracy", "total_messages", "latency_ms_mean"):
        a, b = results["WITH_COMMUNICATION"].get(metric), results["WITHOUT_COMMUNICATION"].get(metric)
        fmt = (lambda v: f"{v:>20.3f}") if isinstance(a, float) else (lambda v: f"{str(v):>20}")
        print(f"{metric:<38}{fmt(a)}{fmt(b)}")

    print("\nper-case governance outcome (the causal trace):")
    print(f"{'case':<8}{'communication_class':<28}{'with':<14}{'without':<14}{'differs'}")
    for row_a, row_b in zip(all_rows["WITH_COMMUNICATION"], all_rows["WITHOUT_COMMUNICATION"]):
        if row_a["governance_action"] is None and row_b["governance_action"] is None:
            continue
        differs = row_a["governance_action"] != row_b["governance_action"]
        print(f"{row_a['case_id']:<8}{row_a['communication_class']:<28}"
              f"{str(row_a['governance_action']):<14}{str(row_b['governance_action']):<14}"
              f"{'YES' if differs else 'no'}")

    for arm in ARMS:
        run_id = record_run(
            experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
            model="none (governance path; embeddings only)",
            configuration={"arm": arm, "git_commit": commit},
            notes="communication ablation with a channel-integrity precondition",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=results[arm])

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"agent_communication_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "git_commit": commit,
                   "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                   "channel_integrity": integrity, "results": results, "rows": all_rows},
                  f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
