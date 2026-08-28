import pytest

from controlplane.decision.engine import ControlAction, ControlDecision
from controlplane.intervention.engine import InterventionEngine, InterventionType


def _decision(action: ControlAction, attempt_number: int = 1) -> ControlDecision:
    return ControlDecision(action=action, reason="test", attempt_number=attempt_number, can_retry=True)


def test_retrieve_more_widens_k():
    spec = InterventionEngine(retrieve_more_k=10).plan(_decision(ControlAction.RETRIEVE_MORE), current_model_role="FAST")
    assert spec.intervention_type == InterventionType.RETRIEVE_MORE
    assert spec.new_rag_k == 10


def test_change_model_escalates_to_strong():
    spec = InterventionEngine().plan(_decision(ControlAction.CHANGE_MODEL), current_model_role="FAST")
    assert spec.intervention_type == InterventionType.CHANGE_MODEL
    assert spec.new_model_role == "STRONG"


def test_regenerate_keeps_the_same_role():
    spec = InterventionEngine().plan(_decision(ControlAction.REGENERATE), current_model_role="STRONG")
    assert spec.new_model_role == "STRONG"


def test_non_retry_action_rejected():
    with pytest.raises(ValueError):
        InterventionEngine().plan(_decision(ControlAction.CONTINUE), current_model_role="FAST")
