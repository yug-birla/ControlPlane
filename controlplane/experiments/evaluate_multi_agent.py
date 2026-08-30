"""Does multi-agent collaboration actually IMPROVE ControlPlane?

Milestone 14 (§4-§16). The architecture already demonstrates that agents
*can* communicate. That is not the question. This experiment asks whether
communication, parallelism, and multi-agent decomposition change the
OUTCOME -- and it is designed so that the answer is allowed to be "no".

THE FOUR CONDITIONS (identical queries, identical base model, identical
scoring; only the architecture differs):

  A  SINGLE_AGENT       Multi-agent planning disabled. Plain capability
                        nodes fetch evidence; one agent acts if the query
                        is agentic. This is the pre-Milestone-12 shape.

  B  MULTI_SEQUENTIAL   Gatherer agents, but serialized: each gatherer
                        depends on the previous one, so the scheduler
                        cannot overlap them. Isolates the cost of
                        decomposition from the benefit of parallelism.

  C  MULTI_PARALLEL     Gatherer agents with no inter-dependencies --
                        the shipped configuration.

  D  MULTI_PARALLEL_NO_COMMS
                        Identical to C, with the agent bus suppressed.
                        The ONLY difference from C is whether handoff
                        messages are recorded and available. This is the
                        controlled test of communication's value.

WHY D IS CONSTRUCTED THIS WAY. §51 requires proving communication helps
rather than asserting it because events exist. If C and D score
identically, the honest conclusion is that communication is currently
*observability*, not *capability* -- valuable for governance and audit,
but not something that changes an answer. That is a real and reportable
finding, not a failure of the experiment.

RAM SAFETY: one model instance, loaded once, shared across all four
conditions. Conditions differ only in runtime wiring.

Run (CPU-only; expect ~1-2 hours):
    .venv/Scripts/python -m controlplane.experiments.evaluate_multi_agent
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.context import RequestContext
from controlplane.experiments.evaluate_baseline_vs_controlplane import (
    BENCHMARK_MODEL_ROLE,
    _contains_any,
)
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.models.registry import get_configured_provider
from controlplane.runtime import build_default_runtime
from controlplane.state import ExecutionState

_DATASET_PATH = Path("data/raw/generated/multi_agent_cases.json")
DATASET_ID = "multi_agent_cases"
DATASET_VERSION = "v0.1"

CONDITIONS = ("A_single_agent", "B_multi_sequential", "C_multi_parallel", "D_multi_no_comms")


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


class _SerializingPlanner:
    """Wraps the real planner and chains gatherers into a dependency
    line, so the scheduler cannot overlap them.

    Deliberately reuses the real planner rather than reimplementing one:
    the point is to isolate PARALLELISM, so everything else about the
    plan -- agent count, roles, permissions -- must stay identical.
    """

    def __init__(self, inner):
        self._inner = inner

    def plan(self, **kwargs):
        return self._inner.plan(**kwargs)

    def apply(self, graph, plan):
        added = self._inner.apply(graph, plan)
        from controlplane.governance.multi_agent import AgentRole

        gatherers = [a.agent_id for a in plan.agents if a.role is not AgentRole.NOTIFIER]
        for i, node_id in enumerate(gatherers[1:], start=1):
            node = graph.get(node_id)
            node.depends_on = tuple(sorted(set(node.depends_on) | {gatherers[i - 1]}))
        if added:
            graph.validate()
        return added


class _SilentBus:
    """An agent bus that records nothing.

    Not a no-op stub that breaks the runtime: it satisfies the same
    interface so execution proceeds normally. Only the messages
    disappear, which is exactly the variable under test.
    """

    def __init__(self):
        self.messages: list = []

    def send(self, message):
        return message

    def triage_replan_request(self, message, **kwargs):
        from controlplane.governance.agent_bus import RequestTriage, TriageResult

        return TriageResult(triage=RequestTriage.REJECT, reason="communication disabled for this condition")


def _build_runtime(condition: str):
    from controlplane.planning.agent_planner import AgentPlanner
    from controlplane.routing.capability_router import CapabilityRouter

    def factory(settings, role=BENCHMARK_MODEL_ROLE):
        return get_configured_provider(settings, role=BENCHMARK_MODEL_ROLE)

    if condition == "A_single_agent":
        # A planner that never proposes gatherers. The router then falls
        # back to plain capability nodes plus at most one actor agent.
        class _NoMultiAgentPlanner(AgentPlanner):
            def plan(self, **kwargs):
                return super().plan(**{**kwargs, "data_requirements": set()})

        router = CapabilityRouter(agent_planner=_NoMultiAgentPlanner())
    elif condition == "B_multi_sequential":
        router = CapabilityRouter(agent_planner=_SerializingPlanner(AgentPlanner()))
    else:
        router = CapabilityRouter()

    runtime = build_default_runtime(provider_factory=factory, capability_router=router)
    if condition == "D_multi_no_comms":
        runtime._agent_bus = _SilentBus()
    return runtime


def _run_case(runtime, case: dict) -> dict:
    ctx = RequestContext.new()
    started = time.monotonic()
    try:
        with ctx.bind():
            state = ExecutionState.initial(ctx=ctx, query=case["query"])
            state = runtime.handle(ctx, state)
        failed = False
        answer = state.metadata.get("answer")
        graph = (state.metadata.get("capability_route") or {}).get("graph", {})
        decision = (state.metadata.get("decision") or {}).get("action")
    except Exception as exc:  # a condition must not silently drop a case
        failed, answer, graph, decision = True, None, {}, f"ERROR: {type(exc).__name__}"
    latency_ms = int((time.monotonic() - started) * 1000)

    nodes = graph.get("nodes") or []
    agent_nodes = [n for n in nodes if n.get("capability") == "AGENT"]
    independent = [n for n in agent_nodes if not n.get("depends_on")]

    expected = case.get("expected_values") or []
    correct = bool(expected) and answer is not None and _contains_any(answer, expected)

    composition = getattr(runtime, "_composition_assessment", None)
    messages = getattr(getattr(runtime, "_agent_bus", None), "messages", [])

    return {
        "case_id": case["case_id"],
        "task_type": case["task_type"],
        "agent_count": len(agent_nodes),
        "expected_agent_count": case["expected_agent_count"],
        "agent_count_matches_plan": len(agent_nodes) == case["expected_agent_count"],
        # COUNT IS NOT COMPOSITION. MA-008 expects ANALYST + NOTIFIER and,
        # once the router's agent gate was widened, produced RETRIEVER +
        # ANALYST -- two agents, matching the expected count, testing
        # nothing the case was written to test. A count-only metric scores
        # that as a pass. Roles are what governance reasons about, so the
        # roles are what get compared.
        "agent_roles": sorted(
            (n.get("input_ref") or {}).get("role", "UNKNOWN") for n in agent_nodes
        ),
        "expected_agent_roles": sorted(case.get("expected_roles") or []),
        "agent_roles_match_plan": (
            sorted((n.get("input_ref") or {}).get("role", "UNKNOWN") for n in agent_nodes)
            == sorted(case.get("expected_roles") or [])
        ),
        "concurrent_agents": len(independent),
        "answered": answer is not None,
        "key_fact_correct": correct,
        # Without this flag the aggregate cannot tell "got it wrong" apart
        # from "there was nothing here to get right".
        "scoreable_for_key_fact": bool(expected),
        "decision": decision,
        "composition_risk": composition.risk.value if composition else None,
        "expected_composition_risk": case.get("expected_composition_risk"),
        "message_count": len(messages),
        "latency_ms": latency_ms,
        "request_failed": failed,
    }


def _aggregate(rows: list[dict]) -> dict:
    """
    KEY_FACT_ACCURACY IS SCORED OVER SCOREABLE CASES ONLY.

    It used to divide by every row. Four of the twelve cases carry
    ``expected_values: []`` -- MA-003, MA-007, MA-008 and MA-010 are
    governance and action cases whose correct outcome is a composition
    verdict, not a retrieved fact. ``_run_case`` computes
    ``bool(expected) and ...``, so those four were hard-False in every
    arm, in every run, by construction.

    That put a ceiling of 8/12 = 0.667 on the metric, and the measured
    value was 0.583 = 7/12 in ALL FOUR conditions: the ceiling minus
    exactly one genuine failure (MA-005). The benchmark had one case of
    headroom. It was reported as "multi-agent does not improve quality",
    when what it actually showed was that this measurement could not
    have detected an improvement of any size.

    The four governance cases are still run and still reported -- under
    ``composition_risk_accuracy``, which is the metric that applies to
    them -- and their count is surfaced here so the denominator is
    visible rather than inferred.
    """
    n = len(rows)
    scored = [r for r in rows if r["expected_agent_count"] is not None]
    scoreable = [r for r in rows if r["scoreable_for_key_fact"]]
    latencies = sorted(r["latency_ms"] for r in rows)

    def _pct(p):
        return latencies[min(int(len(latencies) * p), len(latencies) - 1)] if latencies else None

    governance = [r for r in rows if r["expected_composition_risk"]]
    return {
        "sample_count": n,
        "key_fact_scoreable_count": len(scoreable),
        "key_fact_unscoreable_count": n - len(scoreable),
        "key_fact_accuracy": (
            sum(1 for r in scoreable if r["key_fact_correct"]) / len(scoreable)
            if scoreable else None
        ),
        # The pre-fix denominator, kept so the 0.583 figure quoted in
        # earlier reports stays traceable to the run that produced it.
        "key_fact_accuracy_all_rows_legacy": (
            sum(1 for r in rows if r["key_fact_correct"]) / n if n else None
        ),
        "answered_rate": sum(1 for r in rows if r["answered"]) / n if n else None,
        "request_failure_rate": sum(1 for r in rows if r["request_failed"]) / n if n else None,
        "plan_shape_accuracy": (
            sum(1 for r in scored if r["agent_count_matches_plan"]) / len(scored) if scored else None
        ),
        # The stricter of the two, and the one that reflects what
        # composition governance actually consumes.
        "plan_role_accuracy": (
            sum(1 for r in scored if r["agent_roles_match_plan"]) / len(scored) if scored else None
        ),
        "right_count_wrong_roles_count": sum(
            1 for r in scored if r["agent_count_matches_plan"] and not r["agent_roles_match_plan"]
        ),
        # SS6 of the agent directive: an agent-count error has a direction,
        # and the two directions mean opposite things. Too few agents means
        # missing governance; too many means wasted latency and tokens.
        "unnecessary_agent_rate": (
            sum(1 for r in scored if r["agent_count"] > r["expected_agent_count"]) / len(scored)
            if scored else None
        ),
        "missing_agent_rate": (
            sum(1 for r in scored if r["agent_count"] < r["expected_agent_count"]) / len(scored)
            if scored else None
        ),
        "composition_risk_accuracy": (
            sum(1 for r in governance if r["composition_risk"] == r["expected_composition_risk"])
            / len(governance) if governance else None
        ),
        "total_agent_messages": sum(r["message_count"] for r in rows),
        "mean_concurrent_agents": sum(r["concurrent_agents"] for r in rows) / n if n else None,
        "latency_ms_mean": sum(latencies) / n if n else None,
        "latency_ms_p50": _pct(0.50),
        "latency_ms_p95": _pct(0.95),
    }


def main() -> None:
    cases = _load()
    print(f"Loaded {len(cases)} multi-agent cases\n")

    experiment_id = record_experiment(
        experiment_name="multi_agent_value",
        component="multi_agent",
        algorithm="single_vs_sequential_vs_parallel_vs_no_comms",
        algorithm_version="v1",
    )

    results: dict = {}
    all_rows: dict = {}
    for condition in CONDITIONS:
        print(f"=== {condition} ===")
        runtime = _build_runtime(condition)
        rows = []
        for i, case in enumerate(cases, 1):
            row = _run_case(runtime, case)
            rows.append(row)
            print(f"  [{i:>2}/{len(cases)}] {row['case_id']} agents={row['agent_count']} "
                  f"correct={row['key_fact_correct']} msgs={row['message_count']} {row['latency_ms']}ms")
        metrics = _aggregate(rows)
        results[condition] = metrics
        all_rows[condition] = rows
        run_id = record_run(
            experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
            model=f"role={BENCHMARK_MODEL_ROLE}", configuration={"condition": condition},
            notes="12 hand-authored multi-agent cases; SMOKE_TEST scale; CPU-only",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)
        print()

    print("=" * 96)
    header = f"{'METRIC':<32}" + "".join(f"{c.split('_', 1)[1][:14]:>16}" for c in CONDITIONS)
    print(header)
    print("=" * 96)
    for metric in ("key_fact_accuracy", "key_fact_scoreable_count", "answered_rate",
                   "plan_shape_accuracy", "plan_role_accuracy", "right_count_wrong_roles_count",
                   "unnecessary_agent_rate", "missing_agent_rate",
                   "composition_risk_accuracy", "mean_concurrent_agents",
                   "total_agent_messages", "latency_ms_mean", "latency_ms_p95"):
        row = f"{metric:<32}"
        for c in CONDITIONS:
            v = results[c].get(metric)
            row += f"{v:>16.3f}" if isinstance(v, float) else f"{str(v):>16}"
        print(row)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"multi_agent_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID,
                   "dataset_version": DATASET_VERSION, "results": results, "rows": all_rows},
                  f, indent=2, default=str)
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
