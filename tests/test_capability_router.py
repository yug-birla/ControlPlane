from controlplane.policy.baseline import PolicyBaseline
from controlplane.query_intelligence.fingerprint import (
    Actionability,
    Ambiguity,
    CapabilityHint,
    Complexity,
    Impact,
    Intent,
    QueryFingerprint,
    Sensitivity,
)
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import RiskSeverity
from controlplane.routing.capability_router import CapabilityRouter


def _fp(hints: list[CapabilityHint], actionability=Actionability.INFORMATIONAL, impact=Impact.LOW) -> QueryFingerprint:
    return QueryFingerprint(
        intent=Intent.INFORMATIONAL,
        complexity=Complexity.LOW,
        sensitivity=Sensitivity.NONE,
        ambiguity=Ambiguity.LOW,
        impact=impact,
        actionability=actionability,
        capability_hints=hints,
    )


def _policy_for(severity: RiskSeverity):
    return PolicyBaseline().decide(severity)


def test_general_only_produces_single_generation_node():
    route = CapabilityRouter().route(_fp([CapabilityHint.GENERAL]), _risk(), _policy_for(RiskSeverity.NO_ACTION))
    assert route.selected_capabilities == ["GENERAL"]
    assert [n.node_id for n in route.graph.nodes] == ["generation"]
    assert route.graph.get("generation").depends_on == ()


def test_sql_and_rag_run_in_parallel_before_a_merge_then_generation():
    route = CapabilityRouter().route(
        _fp([CapabilityHint.SQL, CapabilityHint.RAG]), _risk(), _policy_for(RiskSeverity.NO_ACTION)
    )
    node_ids = {n.node_id for n in route.graph.nodes}
    assert node_ids == {"data_sql", "data_rag", "merge", "generation"}
    assert set(route.graph.get("merge").depends_on) == {"data_sql", "data_rag"}
    assert route.graph.get("generation").depends_on == ("merge",)
    assert route.graph.get("data_sql").depends_on == ()
    assert route.graph.get("data_rag").depends_on == ()


def test_agent_capability_adds_a_node_after_generation():
    route = CapabilityRouter().route(
        _fp([CapabilityHint.GENERAL, CapabilityHint.AGENT]), _risk(), _policy_for(RiskSeverity.LOW_RISK)
    )
    assert route.graph.get("agent_action").depends_on == ("generation",)


def test_high_risk_policy_restricts_agent_capability_out_of_the_route():
    route = CapabilityRouter().route(
        _fp([CapabilityHint.GENERAL, CapabilityHint.AGENT], actionability=Actionability.AGENTIC, impact=Impact.HIGH),
        _risk(),
        _policy_for(RiskSeverity.HIGH_RISK),
    )
    assert "AGENT" not in route.selected_capabilities
    assert "AGENT" in route.restricted_removed
    assert "agent_action" not in {n.node_id for n in route.graph.nodes}


def test_multi_source_hint_itself_never_becomes_a_graph_node():
    route = CapabilityRouter().route(
        _fp([CapabilityHint.SQL, CapabilityHint.MULTI_SOURCE]), _risk(), _policy_for(RiskSeverity.NO_ACTION)
    )
    assert "MULTI_SOURCE" not in route.selected_capabilities
    assert all(n.capability != "MULTI_SOURCE" for n in route.graph.nodes)


def test_empty_selection_floors_to_general():
    # Everything restricted -> must not produce an empty, unroutable request.
    route = CapabilityRouter().route(
        _fp([CapabilityHint.AGENT], actionability=Actionability.AGENTIC, impact=Impact.CRITICAL),
        _risk(),
        _policy_for(RiskSeverity.CRITICAL),
    )
    assert route.selected_capabilities == ["GENERAL"]


def _risk():
    fp = _fp([CapabilityHint.GENERAL])
    return BaselineRiskProfiler().profile("placeholder query", fp)
