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


def test_critical_action_policy_restricts_agent_capability_out_of_the_route():
    """AGENT is only policy-restricted at CRITICAL_ACTION now (changed
    this milestone -- see controlplane/policy/baseline.py)."""
    route = CapabilityRouter().route(
        _fp([CapabilityHint.GENERAL, CapabilityHint.AGENT], actionability=Actionability.AGENTIC, impact=Impact.CRITICAL),
        _risk(),
        _policy_for(RiskSeverity.CRITICAL),
    )
    assert "AGENT" not in route.selected_capabilities
    assert "AGENT" in route.restricted_removed
    assert "agent_action" not in {n.node_id for n in route.graph.nodes}


def test_high_risk_policy_no_longer_restricts_agent_capability():
    route = CapabilityRouter().route(
        _fp([CapabilityHint.GENERAL, CapabilityHint.AGENT], actionability=Actionability.AGENTIC, impact=Impact.HIGH),
        _risk(),
        _policy_for(RiskSeverity.HIGH_RISK),
    )
    assert "AGENT" in route.selected_capabilities
    assert "agent_action" in {n.node_id for n in route.graph.nodes}


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


# ---------------------------------------------------------------------------
# REACHABILITY. The defect these cover was not a wrong result -- it was a
# correct result no production input could ever produce.
#
# AgentPlanner has an explicit branch for two independent gatherers on a
# NON-agentic task, and six unit tests in test_agent_planner.py assert its
# behaviour. But this router consulted the planner only when
# CapabilityHint.AGENT was selected, and passed is_agentic=True as a
# literal. So no request could reach that branch: the tests exercised an
# input the runtime could not generate, and passed forever.
#
# Measured cost: six of eight agent-expecting cases in the multi-agent
# benchmark ran with zero agents, and the four ablation conditions were
# the same execution path on nine of twelve cases -- which is why they
# returned byte-identical quality and were written up as "multi-agent does
# not help".
#
# A unit test proves a function does what it says. Only a test at the
# integration boundary proves anything ever calls it that way.
# ---------------------------------------------------------------------------


def _fp_with_sources(hints, sources, actionability=Actionability.INFORMATIONAL):
    fp = _fp(hints, actionability=actionability)
    fp.data_requirement = list(sources)
    return fp


def test_two_independent_sources_reach_the_planner_without_an_agentic_query():
    """The reachability guard. A read-only two-source query must produce
    gatherer agents; if this fails, AgentPlanner's non-agentic branch has
    become unreachable again and its unit tests are certifying dead code."""
    from controlplane.query_intelligence.fingerprint import DataRequirement

    route = CapabilityRouter().route(
        _fp_with_sources(
            [CapabilityHint.SQL, CapabilityHint.RAG],
            [DataRequirement.RAG_CORPUS, DataRequirement.SQL_DB],
        ),
        _risk(),
        _policy_for(RiskSeverity.NO_ACTION),
    )
    agent_nodes = [n for n in route.graph.nodes if n.capability == CapabilityHint.AGENT.value]
    assert len(agent_nodes) == 2, [n.node_id for n in route.graph.nodes]
    # ...and they must be independent, or the parallelism is a label only.
    for node in agent_nodes:
        assert node.depends_on == ()


def test_a_read_only_query_gets_gatherers_but_never_an_actor():
    """The gate was widened, not removed. An informational query must not
    acquire a NOTIFIER: an actor exists to perform an action, and there is
    no action here to perform."""
    from controlplane.query_intelligence.fingerprint import DataRequirement

    route = CapabilityRouter().route(
        _fp_with_sources(
            [CapabilityHint.SQL, CapabilityHint.RAG],
            [DataRequirement.RAG_CORPUS, DataRequirement.SQL_DB],
        ),
        _risk(),
        _policy_for(RiskSeverity.NO_ACTION),
    )
    assert "agent_action" not in {n.node_id for n in route.graph.nodes}


def test_one_servable_source_still_produces_no_agents():
    """The planner's minimum-complexity rule must survive the widening.
    One source and no action is a plain capability path, not an agent."""
    from controlplane.query_intelligence.fingerprint import DataRequirement

    route = CapabilityRouter().route(
        _fp_with_sources([CapabilityHint.RAG], [DataRequirement.RAG_CORPUS]),
        _risk(),
        _policy_for(RiskSeverity.NO_ACTION),
    )
    assert not [n for n in route.graph.nodes if n.capability == CapabilityHint.AGENT.value]
    assert "data_rag" in {n.node_id for n in route.graph.nodes}


def test_gatherers_do_not_swallow_data_sources_they_cannot_serve():
    """Gatherers replace the plain data nodes they serve -- RAG and SQL --
    and nothing else. Dropping every data node whenever any gatherer
    existed lost WEB/CHAT_HISTORY evidence silently, and made the
    multi-agent ablation asymmetric: the two arms differed by more than
    the variable under test."""
    from controlplane.query_intelligence.fingerprint import DataRequirement

    route = CapabilityRouter().route(
        _fp_with_sources(
            [CapabilityHint.SQL, CapabilityHint.RAG, CapabilityHint.WEB],
            [DataRequirement.RAG_CORPUS, DataRequirement.SQL_DB, DataRequirement.WEB_SEARCH],
        ),
        _risk(),
        _policy_for(RiskSeverity.NO_ACTION),
    )
    node_ids = {n.node_id for n in route.graph.nodes}
    assert "data_web" in node_ids, node_ids
    assert "data_rag" not in node_ids and "data_sql" not in node_ids
    assert set(route.graph.get("merge").depends_on) == {
        "agent_retriever", "agent_analyst", "data_web",
    }


def test_a_data_requirement_the_route_did_not_select_gets_no_agent():
    """`data_requirement` and `capability_hints` come from two independent
    votes and can disagree. "trigger a failure" -- a meaningless test
    string -- profiles to hints ['GENERAL'] and data requirements
    [MEMORY_STORE, RAG_CORPUS, SQL_DB, WEB_SEARCH].

    Reading data_requirement alone turned that noise into two live
    retrieval agents fetching evidence the route never chose. A gatherer
    organises work the plan already selected; it does not add work.
    """
    from controlplane.query_intelligence.fingerprint import DataRequirement

    route = CapabilityRouter().route(
        _fp_with_sources(
            [CapabilityHint.GENERAL],
            [DataRequirement.RAG_CORPUS, DataRequirement.SQL_DB],
        ),
        _risk(),
        _policy_for(RiskSeverity.NO_ACTION),
    )
    assert not [n for n in route.graph.nodes if n.capability == CapabilityHint.AGENT.value]
    assert [n.node_id for n in route.graph.nodes] == ["generation"]


def test_only_the_agreed_capabilities_become_gatherers():
    """RAG is selected and SQL is not, so exactly one gatherer is
    justified -- and one gatherer without an action is no agents at all."""
    from controlplane.query_intelligence.fingerprint import DataRequirement

    route = CapabilityRouter().route(
        _fp_with_sources(
            [CapabilityHint.RAG],
            [DataRequirement.RAG_CORPUS, DataRequirement.SQL_DB],
        ),
        _risk(),
        _policy_for(RiskSeverity.NO_ACTION),
    )
    node_ids = {n.node_id for n in route.graph.nodes}
    assert not [n for n in route.graph.nodes if n.capability == CapabilityHint.AGENT.value]
    assert "data_rag" in node_ids
    assert "data_sql" not in node_ids
