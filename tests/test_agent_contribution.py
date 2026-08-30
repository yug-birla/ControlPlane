"""Did each agent earn its place?

The multi-agent benchmark could report agent counts, message counts and
latency, and could not answer the question that decides whether
decomposition was worth anything. These pin the answer, including the
uncomfortable direction: an agent that duplicates another agent's work
must be reported as redundant rather than counted as participation.
"""

from __future__ import annotations

from controlplane.governance.contribution import (
    ContributionVerdict,
    measure_contributions,
    summarise,
)


def _gatherer(items, *, role="RETRIEVER", capability="RAG"):
    return {
        "serves_capability": capability,
        "agent_role": role,
        "evidence": [{"text": t} for t in items],
    }


def _actor(*, from_agents=(), influence="NONE"):
    return {
        "agent_role": "NOTIFIER",
        "proposed_tool": "send_notification",
        "handoff_received": {"from_agents": list(from_agents)} if from_agents else None,
        "handoff_influence": influence,
    }


def test_an_agent_that_duplicates_another_is_reported_redundant():
    """The finding the framework exists to make possible. Two agents,
    identical evidence, and the second added nothing the request did not
    already have."""
    results = [
        ("agent_retriever", _gatherer(["Tier 1 hotel allowance is $250 per night"])),
        ("agent_analyst", _gatherer(["Tier 1 hotel allowance is $250 per night"], capability="SQL")),
    ]
    contributions = {c.agent_id: c for c in measure_contributions(agent_results=results)}

    for agent_id in ("agent_retriever", "agent_analyst"):
        assert contributions[agent_id].verdict is ContributionVerdict.REDUNDANT
        assert contributions[agent_id].unique_evidence == 0
        assert contributions[agent_id].duplicate_evidence == 1
        assert contributions[agent_id].information_gain == 0.0


def test_whitespace_and_case_do_not_manufacture_uniqueness():
    """Two agents quoting the same passage differently have not each
    contributed it."""
    results = [
        ("agent_retriever", _gatherer(["Tier 1 hotel allowance is $250 per night"])),
        ("agent_analyst", _gatherer(["tier 1  HOTEL allowance   is $250 per night"])),
    ]
    contributions = measure_contributions(agent_results=results)
    assert all(c.unique_evidence == 0 for c in contributions)


def test_complementary_agents_are_both_contributing():
    results = [
        ("agent_retriever", _gatherer(["Tier 1 hotel allowance is $250 per night"])),
        ("agent_analyst", _gatherer(["Q4 revenue was $410,000"], capability="SQL")),
    ]
    contributions = {c.agent_id: c for c in measure_contributions(agent_results=results)}
    for agent_id in ("agent_retriever", "agent_analyst"):
        assert contributions[agent_id].unique_evidence == 1
        assert contributions[agent_id].information_gain == 1.0
        assert contributions[agent_id].verdict is ContributionVerdict.CONTRIBUTING


def test_evidence_that_reaches_the_answer_is_essential():
    results = [("agent_analyst", _gatherer(["Q4 revenue was 410000 dollars"], capability="SQL"))]
    contributions = measure_contributions(
        agent_results=results,
        answer="Q4 revenue was 410000 dollars across all regions.",
    )
    assert contributions[0].answer_influence is True
    assert contributions[0].verdict is ContributionVerdict.ESSENTIAL


def test_an_unrelated_answer_does_not_count_as_influence():
    """The guard on a lexical proxy: without it every agent would look
    essential whenever the answer happened to be wordy."""
    results = [("agent_analyst", _gatherer(["Q4 revenue was 410000 dollars"], capability="SQL"))]
    contributions = measure_contributions(
        agent_results=results,
        answer="The hotel allowance in Tier 1 cities is 250 per night.",
    )
    assert contributions[0].answer_influence is False
    assert contributions[0].verdict is ContributionVerdict.CONTRIBUTING


def test_influence_comes_from_the_receiver_not_from_the_message_existing():
    """SS19. A handoff that arrived and changed nothing is not influence;
    one that changed the receiver's decision is."""
    observed = [
        ("agent_analyst", _gatherer(["customer contact records"], capability="SQL")),
        ("agent_action", _actor(from_agents=("agent_analyst",), influence="OBSERVED_ONLY")),
    ]
    changed = [
        ("agent_analyst", _gatherer(["customer contact records"], capability="SQL")),
        ("agent_action", _actor(from_agents=("agent_analyst",), influence="CHANGED_STEP_RISK")),
    ]

    a = {c.agent_id: c for c in measure_contributions(agent_results=observed)}
    b = {c.agent_id: c for c in measure_contributions(agent_results=changed)}

    assert a["agent_analyst"].downstream_influence == "OBSERVED_ONLY"
    assert a["agent_analyst"].verdict is ContributionVerdict.CONTRIBUTING

    assert b["agent_analyst"].downstream_influence == "CHANGED_STEP_RISK"
    assert b["agent_analyst"].verdict is ContributionVerdict.ESSENTIAL


def test_an_agent_that_produced_and_influenced_nothing_is_inert():
    results = [("agent_retriever", _gatherer([]))]
    contributions = measure_contributions(agent_results=results)
    assert contributions[0].verdict is ContributionVerdict.INERT
    assert contributions[0].evidence_contributed == 0


def test_the_summary_prices_the_agents_that_were_not_worth_running():
    results = [
        ("agent_retriever", _gatherer(["Tier 1 hotel allowance is $250 per night"])),
        ("agent_analyst", _gatherer(["Tier 1 hotel allowance is $250 per night"], capability="SQL")),
        ("agent_web", _gatherer([])),
    ]
    contributions = measure_contributions(
        agent_results=results,
        latencies_ms={"agent_retriever": 800.0, "agent_analyst": 1200.0, "agent_web": 300.0},
    )
    summary = summarise(contributions)

    assert summary["agent_count"] == 3
    assert summary["redundant_count"] == 2
    assert summary["inert_count"] == 1
    assert summary["wasted_agent_rate"] == 1.0
    assert summary["wasted_latency_ms"] == 2300.0


def test_dimensions_are_reported_separately_not_collapsed():
    """SS11 is explicit that this must not become one opaque score."""
    results = [("agent_analyst", _gatherer(["Q4 revenue was $410,000"], capability="SQL"))]
    record = measure_contributions(agent_results=results)[0].to_dict()
    for field in (
        "evidence_contributed", "unique_evidence", "duplicate_evidence",
        "information_gain", "downstream_influence", "answer_influence",
        "latency_ms", "verdict", "reason",
    ):
        assert field in record, field
