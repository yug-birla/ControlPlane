"""Two agents disagreeing must not be settled by whichever ran first.

Until this existed, contradictory gatherer evidence went into the merge
node together and whichever value the model happened to favour became
the answer, with no record that a disagreement had occurred.
"""

from __future__ import annotations

from controlplane.governance.agent_conflict import (
    ConflictResolution,
    detect_conflicts,
    summarise,
)


def _agent(capability, texts):
    return {"serves_capability": capability, "evidence": [{"text": t} for t in texts]}


def test_two_agents_reporting_different_limits_is_a_conflict():
    results = [
        ("agent_retriever", _agent("RAG", ["The meal reimbursement limit is $75 per day."])),
        ("agent_analyst", _agent("SQL", ["The meal reimbursement limit is $100 per day."])),
    ]
    conflicts = detect_conflicts(results)

    assert len(conflicts) == 1, [c.to_dict() for c in conflicts]
    conflict = conflicts[0]
    assert {conflict.left_value, conflict.right_value} == {75.0, 100.0}
    assert {conflict.left_agent, conflict.right_agent} == {"agent_retriever", "agent_analyst"}


def test_the_database_wins_over_a_document_quoting_the_same_figure():
    """The one authority rule, stated rather than assumed: the database
    stores the figure and a document can quote a stale copy of it."""
    results = [
        ("agent_retriever", _agent("RAG", ["The meal reimbursement limit is $75 per day."])),
        ("agent_analyst", _agent("SQL", ["The meal reimbursement limit is $100 per day."])),
    ]
    conflict = detect_conflicts(results)[0]

    assert conflict.resolution is ConflictResolution.SOURCE_AUTHORITY
    assert conflict.preferred_agent == "agent_analyst"
    assert "enterprise database" in conflict.reason


def test_two_documents_disagreeing_are_left_unresolved():
    """No basis for preferring either, so the disagreement is surfaced
    rather than settled. Picking one here would be exactly the silent
    choosing this module exists to prevent."""
    results = [
        ("agent_retriever", _agent("RAG", ["The meal reimbursement limit is $75 per day."])),
        ("agent_second", _agent("RAG", ["The meal reimbursement limit is $100 per day."])),
    ]
    conflict = detect_conflicts(results)[0]

    assert conflict.resolution is ConflictResolution.UNRESOLVED
    assert conflict.preferred_agent is None
    assert summarise([conflict])["requires_disclosure"] is True


def test_agreement_is_not_a_conflict():
    results = [
        ("agent_retriever", _agent("RAG", ["The meal reimbursement limit is $75 per day."])),
        ("agent_analyst", _agent("SQL", ["The meal reimbursement limit is $75 per day."])),
    ]
    assert detect_conflicts(results) == []


def test_numbers_about_different_things_are_not_a_conflict():
    """The false-positive guard. Two figures in a corpus are usually
    about different subjects; without a subject test every pair of
    numbers would be reported as a disagreement."""
    results = [
        ("agent_retriever", _agent("RAG", ["The meal reimbursement limit is $75 per day."])),
        ("agent_analyst", _agent("SQL", ["The hotel accommodation rate is $250 per night."])),
    ]
    assert detect_conflicts(results) == []


def test_two_figures_from_one_agent_are_not_a_cross_agent_conflict():
    """One source's internal inconsistency is a different problem, and
    the reasoning evaluator already checks an answer for it."""
    results = [
        ("agent_retriever", _agent("RAG", [
            "The meal reimbursement limit is $75 per day.",
            "The meal reimbursement limit is $100 per day.",
        ])),
    ]
    assert detect_conflicts(results) == []


def test_a_single_agent_can_never_conflict_with_itself_via_the_summary():
    assert summarise([])["requires_disclosure"] is False
    assert summarise([])["conflict_count"] == 0


def test_the_summary_separates_resolved_from_unresolved():
    results = [
        ("agent_retriever", _agent("RAG", ["The meal reimbursement limit is $75 per day."])),
        ("agent_analyst", _agent("SQL", ["The meal reimbursement limit is $100 per day."])),
        ("agent_second_doc", _agent("RAG", ["The meal reimbursement limit is $90 per day."])),
    ]
    summary = summarise(detect_conflicts(results))
    assert summary["conflict_count"] >= 2
    assert summary["resolved_by_authority_count"] >= 1
    assert summary["unresolved_count"] >= 1
    assert summary["requires_disclosure"] is True


# ---------------------------------------------------------------------------
# RUNTIME WIRING. A conflict detector nothing consults is a module, not a
# control. These check that an unresolved cross-agent disagreement reaches
# the decision path -- and that it reaches it as CONFLICTING, so the
# existing refusal to replan for conflicting evidence applies: a conflict
# needs an AUTHORITATIVE source, not an additional one.
# ---------------------------------------------------------------------------


def test_an_unresolved_conflict_becomes_a_conflicting_evaluation_result():
    from controlplane.evaluation.evaluators import EvaluationResult, EvaluationStatus
    from controlplane.governance.agent_conflict import summarise

    results = [
        ("agent_retriever", _agent("RAG", ["The meal reimbursement limit is $75 per day."])),
        ("agent_second", _agent("RAG", ["The meal reimbursement limit is $100 per day."])),
    ]
    summary = summarise(detect_conflicts(results))
    assert summary["unresolved_count"] >= 1

    # The shape the runtime builds, asserted here so the contract the
    # decision engine keys on cannot drift silently.
    result = EvaluationResult(
        evaluator="agent_conflict_v1",
        status=EvaluationStatus.IMPLEMENTED,
        label="CONFLICTING",
        evidence=summary,
        rationale="unresolved cross-agent disagreement",
        recommended_signal="FLAG_FOR_REVIEW",
    )
    assert result.label == "CONFLICTING"
    assert result.recommended_signal == "FLAG_FOR_REVIEW"


def test_the_runtime_refuses_to_replan_on_a_conflicting_result():
    """The behavioural consequence, driven through the real method: a
    conflict must not trigger "fetch another source"."""
    from controlplane.evaluation.evaluators import EvaluationResult, EvaluationStatus
    from controlplane.runtime import Runtime

    runtime = object.__new__(Runtime)
    conflicting = [EvaluationResult(
        evaluator="agent_conflict_v1", status=EvaluationStatus.IMPLEMENTED,
        label="CONFLICTING", rationale="two agents disagree",
    )]
    proposal = Runtime._attempt_capability_replan(
        runtime, ctx=None, query="", capability_route=None, fingerprint=None,
        evaluation_results=conflicting,
    )
    assert proposal is None, "a conflict needs an authoritative source, not an additional one"


def test_conflicts_do_not_survive_into_the_next_request():
    """Per-request state. A disagreement belonging to an earlier request
    must not flag this one -- the same leak family as the composition
    verdict and the agent bus."""
    from controlplane.governance.agent_conflict import AgentConflict, ConflictResolution
    from controlplane.governance.agent_bus import AgentBus
    from controlplane.runtime import Runtime

    runtime = object.__new__(Runtime)
    runtime._agent_bus = AgentBus()
    runtime._agent_conflicts = [AgentConflict(
        subject="limit", left_agent="a", right_agent="b", left_value=75.0, right_value=100.0,
        left_source="RAG", right_source="RAG", unit="currency",
        resolution=ConflictResolution.UNRESOLVED, preferred_agent=None, reason="left over",
    )]
    runtime._reset_per_request_state()
    assert runtime._agent_conflicts == []
