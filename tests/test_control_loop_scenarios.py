"""End-to-end control-loop scenarios: Decision -> Intervention -> Replan
-> Verification actually changing execution, not just observing it
(bootstrap's core acceptance criterion). Each test uses a scripted fake
provider (never the live API) whose answers are deliberately chosen to
exercise a specific control-loop path -- the routing/decision/
intervention/verification logic itself is 100% real; only the model's
canned text is scripted, exactly like ``tests/fakes.py``'s existing
``FakeModelProvider``/``FailingModelProvider``.
"""

from __future__ import annotations

from controlplane.context import RequestContext
from controlplane.decision.engine import ControlAction
from controlplane.events.store import EventStore
from controlplane.models.provider import ModelProvider, ModelResult
from controlplane.runtime import build_default_runtime
from controlplane.state import ExecutionState
from controlplane.trajectory.store import TrajectoryStore
from controlplane.verification.engine import VerificationStatus


class _ScriptedProvider(ModelProvider):
    name = "scripted"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    def generate(self, *, prompt: str) -> ModelResult:
        content = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return ModelResult(provider=self.name, model="fake-scripted", content=content, latency_ms=1, finish_reason="stop")


def _run(query: str, provider: ModelProvider) -> tuple[ExecutionState, RequestContext]:
    rt = build_default_runtime(provider_factory=lambda settings, role="STRONG": provider)
    ctx = RequestContext.new()
    with ctx.bind():
        state = ExecutionState.initial(ctx=ctx, query=query)
        state = rt.handle(ctx, state)
    return state, ctx


def test_rag_self_healing_recovers_from_an_ungrounded_first_answer():
    """SCENARIO 5 (mandatory): insufficient grounding -> detect ->
    intervene (RETRIEVE_MORE) -> replan -> retrieve again -> re-evaluate
    -> verify -> a genuinely better, grounded final answer."""
    provider = _ScriptedProvider([
        "The weather forecast predicts rain tomorrow across the region.",  # attempt 1: ungrounded
        "Meal reimbursement is up to $75/day domestic, $100/day international, per the travel policy.",  # attempt 2: grounded
    ])
    state, ctx = _run("What is the meal reimbursement limit according to the travel policy?", provider)

    assert provider.calls == 2  # the model really was called twice, not just evaluated twice
    assert "75/day" in state.metadata["answer"]
    assert state.metadata["decision"]["action"] == ControlAction.CONTINUE.value
    assert state.metadata["decision"]["attempt_number"] == 2
    assert state.metadata["verification"]["status"] == VerificationStatus.VERIFIED.value

    events = [e["event_type"] for e in EventStore().get_by_trajectory(ctx.trajectory_id)]
    assert "RETRIEVAL_INSUFFICIENT" in events
    assert "INTERVENTION_TRIGGERED" in events
    assert "REPLAN_TRIGGERED" in events
    assert "REPLAN_COMPLETED" in events
    assert events.count("MODEL_CALLED") == 2

    steps = [h["step_type"] for h in TrajectoryStore().get_history(ctx.trajectory_id)]
    assert steps.count("decision:1") == 1 and steps.count("decision:2") == 1


def test_rag_self_healing_exhausts_budget_and_asks_for_clarification():
    """If the retry ALSO fails to ground the answer, the loop must stop
    (bounded self-healing) and not silently return a bad answer as if it
    were fine."""
    provider = _ScriptedProvider([
        "The weather forecast predicts rain tomorrow across the region.",
        "Our quarterly sports league standings were updated yesterday.",
    ])
    state, _ctx = _run("What is the meal reimbursement limit according to the travel policy?", provider)

    assert provider.calls == 2
    assert state.metadata["answer"] is None
    assert state.metadata["decision"]["action"] == ControlAction.ASK_CLARIFICATION.value
    assert state.metadata["decision"]["can_retry"] is False
    assert state.metadata["verification"]["status"] == VerificationStatus.NOT_VERIFIED.value


def test_low_confidence_fast_response_escalates_to_strong_model():
    """SCENARIO 8 / model escalation: a hedging fast-model response
    triggers CHANGE_MODEL; the second (STRONG-role) call produces a
    confident final answer."""
    provider = _ScriptedProvider([
        "I'm not sure, it's unclear to me.",
        "The capital of France is Paris, a well-established fact.",
    ])
    state, ctx = _run("What is the capital of France?", provider)

    assert provider.calls == 2
    assert "Paris" in state.metadata["answer"]
    assert state.metadata["decision"]["action"] == ControlAction.CONTINUE.value  # resolved by attempt 2
    assert state.metadata["model"]["role"] == "STRONG"

    events = [e["event_type"] for e in EventStore().get_by_trajectory(ctx.trajectory_id)]
    assert "MODEL_ESCALATION" in events
    assert "REPLAN_TRIGGERED" in events

    first_decision = next(d for d in TrajectoryStore().get_history(ctx.trajectory_id) if d["step_type"] == "decision:1")
    assert first_decision["output_ref"]["action"] == ControlAction.CHANGE_MODEL.value


class _ScriptedConflictingRAG:
    """A fake RAG capability that always reports CONFLICTING adequacy --
    used because the real 30-document corpus doesn't happen to contain a
    genuine same-topic contradiction, so this exercises the Decision
    Engine's CONFLICTING-evidence branch (controlplane/decision/engine.py)
    deterministically rather than relying on the real corpus to produce
    one by chance."""

    def __init__(self, evidence_texts: list[str]) -> None:
        self._evidence_texts = evidence_texts
        self.calls = 0

    def execute(self, query_text: str, k: int | None = None) -> dict:
        self.calls += 1
        return {
            "status": "EXECUTED",
            "retrieved_count": len(self._evidence_texts),
            "reranked": False,
            "evidence": [
                {"document": f"Doc{i}", "text": t, "dense_score": 0.5, "lexical_score": 0.5, "fused_score": 0.5, "cross_encoder_score": None}
                for i, t in enumerate(self._evidence_texts)
            ],
            "adequacy": {"label": "CONFLICTING", "coverage": 0.8, "reason": "evidence items disagree on a polarity term (test fixture)"},
            "source": "test-fixture",
        }


def test_conflicting_evidence_asks_for_clarification_instead_of_picking_one_value():
    """Bootstrap SS29: conflicting evidence must not be silently resolved
    by picking one of the disputed values -- the loop should retry once
    (in case a wider retrieval surfaces an authoritative source), then
    disclose the conflict rather than assert either figure."""
    fake_rag = _ScriptedConflictingRAG(["[Annex B]: Threshold is $5,000.", "[Finance Addendum]: Threshold is $10,000."])
    provider = _ScriptedProvider(["The threshold is $5,000 per the Annex B policy document."])
    rt = build_default_runtime(provider_factory=lambda settings, role="STRONG": provider, rag_capability=fake_rag)
    ctx = RequestContext.new()
    with ctx.bind():
        state = ExecutionState.initial(ctx=ctx, query="What is the exact financial threshold for SLA commitments per our policy documents?")
        state = rt.handle(ctx, state)

    assert fake_rag.calls == 2  # widened-k retry really did re-run retrieval, not just re-evaluate
    assert state.metadata["answer"] is None  # never silently asserts $5,000 or $10,000
    assert state.metadata["decision"]["action"] == ControlAction.ASK_CLARIFICATION.value
    assert state.metadata["decision"]["triggering_evaluator"] == "rag_adequacy"
    assert state.metadata["verification"]["status"] == VerificationStatus.NOT_VERIFIED.value

    events = [e["event_type"] for e in EventStore().get_by_trajectory(ctx.trajectory_id)]
    assert "INTERVENTION_TRIGGERED" in events
    first_decision = next(d for d in TrajectoryStore().get_history(ctx.trajectory_id) if d["step_type"] == "decision:1")
    assert first_decision["output_ref"]["action"] == ControlAction.RETRIEVE_MORE.value


def test_high_risk_action_reaches_human_review_not_continue():
    """SCENARIO 7: a high-risk action must always terminate at
    HUMAN_REVIEW/REJECTED, never CONTINUE/VERIFIED, regardless of how
    well-grounded or confident the drafted response looks."""
    provider = _ScriptedProvider(["Refund of $50,000 approved and processed for the enterprise account."])
    state, _ctx = _run(
        "Given our recent SOC 2 audit findings regarding access governance, recommend whether we should "
        "implement an automated Identity Governance and Administration (IGA) tool or enhance internal review scripts.",
        provider,
    )

    assert state.metadata["risk"]["severity"] == "HIGH_RISK"
    assert state.metadata["decision"]["action"] == ControlAction.HUMAN_REVIEW.value
    assert state.metadata["decision"]["triggering_evaluator"] == "action_risk"
    assert state.metadata["verification"]["status"] == VerificationStatus.REJECTED.value
    # Graceful degradation, not withholding: a draft is still available for the human to review.
    assert state.metadata["answer"] is not None
