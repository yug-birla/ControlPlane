"""Shadow Mode: observe everything, enforce nothing."""

from __future__ import annotations

from controlplane.decision.engine import ControlAction, ControlDecision
from controlplane.governance.shadow_mode import (
    ShadowVerdict,
    is_would_have_changed_execution,
    verdict_for,
)


def _decision(action: ControlAction) -> ControlDecision:
    return ControlDecision(
        action=action,
        reason="test",
        attempt_number=1,
        requires_intervention=False,
        can_retry=False,
    )


def test_every_control_action_maps_to_a_verdict():
    """The mapping table must stay exhaustive: a ControlAction added
    later without updating shadow_mode.py would silently be recorded as
    WOULD_CONTINUE, i.e. an enforcement action reported as 'no action'."""
    for action in ControlAction:
        verdict = verdict_for(_decision(action))
        if action is ControlAction.CONTINUE:
            assert verdict is ShadowVerdict.WOULD_CONTINUE
        else:
            assert verdict is not ShadowVerdict.WOULD_CONTINUE, (
                f"{action} fell through to the WOULD_CONTINUE default -- "
                "add it to _ACTION_TO_VERDICT"
            )


def test_withholding_actions_map_to_would_block():
    assert verdict_for(_decision(ControlAction.ASK_CLARIFICATION)) is ShadowVerdict.WOULD_BLOCK
    assert verdict_for(_decision(ControlAction.ABSTAIN)) is ShadowVerdict.WOULD_BLOCK


def test_human_review_maps_to_would_escalate():
    assert verdict_for(_decision(ControlAction.HUMAN_REVIEW)) is ShadowVerdict.WOULD_ESCALATE


def test_retrieval_and_model_changes_both_map_to_would_reroute():
    assert verdict_for(_decision(ControlAction.RETRIEVE_MORE)) is ShadowVerdict.WOULD_REROUTE
    assert verdict_for(_decision(ControlAction.CHANGE_MODEL)) is ShadowVerdict.WOULD_REROUTE


def test_only_continue_counts_as_unchanged_execution():
    assert not is_would_have_changed_execution(ShadowVerdict.WOULD_CONTINUE)
    for verdict in ShadowVerdict:
        if verdict is not ShadowVerdict.WOULD_CONTINUE:
            assert is_would_have_changed_execution(verdict)
