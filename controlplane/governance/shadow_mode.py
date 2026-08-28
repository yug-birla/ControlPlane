"""Shadow Mode -- observe and record what ControlPlane WOULD have done,
without enforcing any of it.

Bootstrap SS18/SS39. The deployment story this exists for: an
organization already running an unmanaged LLM application cannot
realistically switch enforcement on blind. Shadow Mode lets ControlPlane
run beside the existing system on real traffic, recording every control
action it would have taken, so the intervention rate, the false-positive
rate, and the would-be blocks can be reviewed BEFORE anything is
enforced.

It is also the honest measurement instrument for this project's central
claim. Enforcing and non-enforcing runs of the same query differ in the
answer returned, which makes "how often would ControlPlane have
intervened on ordinary traffic?" hard to answer from enforced runs
alone. Shadow Mode answers it directly.

WHAT SHADOW MODE DOES NOT CHANGE: query understanding, risk, policy,
routing, execution, and evaluation all run exactly as normal -- the
observations must reflect what the real system would see. Only the
*consequences* are suppressed:

  - no intervention is executed (no re-retrieval, no model escalation,
    no regeneration)
  - no answer is ever withheld (ASK_CLARIFICATION / ABSTAIN still return
    the model's answer)
  - the model-router ABSTAIN path still generates rather than refusing

The recorded verdict vocabulary is the bootstrap's, mapped from the
Decision Engine's own actions so shadow verdicts and enforced actions
can never drift apart:

  WOULD_CONTINUE   the response was acceptable as-is
  WOULD_VERIFY     extra verification would have been requested
  WOULD_REROUTE    retrieval/model would have been changed and retried
  WOULD_INTERVENE  the response would have been regenerated
  WOULD_ESCALATE   a human would have been brought in
  WOULD_BLOCK      the response would have been withheld entirely
"""

from __future__ import annotations

from enum import Enum

from controlplane.decision.engine import ControlAction, ControlDecision


class ShadowVerdict(str, Enum):
    WOULD_CONTINUE = "WOULD_CONTINUE"
    WOULD_VERIFY = "WOULD_VERIFY"
    WOULD_REROUTE = "WOULD_REROUTE"
    WOULD_INTERVENE = "WOULD_INTERVENE"
    WOULD_ESCALATE = "WOULD_ESCALATE"
    WOULD_BLOCK = "WOULD_BLOCK"


# Derived from the Decision Engine's real actions rather than recomputed
# from evaluator output: a shadow verdict must be exactly what the
# enforcing system would have done, not a parallel reimplementation that
# can silently disagree with it.
_ACTION_TO_VERDICT: dict[ControlAction, ShadowVerdict] = {
    ControlAction.CONTINUE: ShadowVerdict.WOULD_CONTINUE,
    ControlAction.VERIFY: ShadowVerdict.WOULD_VERIFY,
    ControlAction.RETRIEVE_MORE: ShadowVerdict.WOULD_REROUTE,
    ControlAction.CHANGE_MODEL: ShadowVerdict.WOULD_REROUTE,
    ControlAction.REGENERATE: ShadowVerdict.WOULD_INTERVENE,
    ControlAction.HUMAN_REVIEW: ShadowVerdict.WOULD_ESCALATE,
    ControlAction.ASK_CLARIFICATION: ShadowVerdict.WOULD_BLOCK,
    ControlAction.ABSTAIN: ShadowVerdict.WOULD_BLOCK,
}


def verdict_for(decision: ControlDecision) -> ShadowVerdict:
    """The shadow verdict corresponding to a real control decision.

    Unmapped actions fall back to WOULD_CONTINUE only if a future action
    is added without updating this table; that would be a bug, so the
    table is asserted complete by
    ``tests/test_shadow_mode.py::test_every_control_action_maps_to_a_verdict``
    rather than left to be discovered in production.
    """
    return _ACTION_TO_VERDICT.get(decision.action, ShadowVerdict.WOULD_CONTINUE)


def is_would_have_changed_execution(verdict: ShadowVerdict) -> bool:
    """True when the enforcing system would have done something an
    unmanaged model would not -- the quantity that matters when deciding
    whether to switch enforcement on."""
    return verdict is not ShadowVerdict.WOULD_CONTINUE
