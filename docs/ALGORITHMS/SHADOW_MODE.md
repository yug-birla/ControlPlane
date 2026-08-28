# Shadow Mode

**Status:** IMPLEMENTED (Milestone 9). Reachable via `build_default_runtime(shadow_mode=True)` / `Runtime(shadow_mode=True)`.
**Code:** `controlplane/governance/shadow_mode.py`, enforcement suppression in `controlplane/runtime.py`.
**Tests:** `tests/test_shadow_mode.py` (unit), `tests/test_control_loop_scenarios.py` (3 end-to-end scenarios).

Spec: bootstrap §18 / §39. This was `NOT_IMPLEMENTED` from Milestone 6 through Milestone 8 — a genuine specified-architecture gap, listed as such in each of those milestones' reports rather than quietly dropped.

## Why It Exists

Two distinct reasons, both real:

**1. Deployment.** An organization already running an unmanaged LLM application cannot switch enforcement on blind. Shadow Mode runs ControlPlane beside the existing system on real traffic and records every control action it *would* have taken, so the intervention rate, the false-positive rate, and the would-be blocks can be reviewed **before** anything is enforced.

**2. Measurement.** "How often would ControlPlane have intervened on ordinary traffic?" is hard to answer from enforced runs, because enforcement changes the answer that gets produced and therefore changes everything measured downstream of it. Shadow Mode answers it directly. It is also the natural *"detect but do not act"* ablation condition — see `controlplane/experiments/evaluate_ablations.py`, condition C.

## What Is And Is Not Suppressed

Everything upstream of a consequence runs **exactly as normal** — the observations must reflect what the real system would see:

| Stage | Shadow Mode |
|---|---|
| Query understanding, risk, policy | runs normally |
| Capability + model routing | runs normally |
| Execution graph (RAG/SQL/Agent) | runs normally |
| Evaluation suite | runs normally |
| Decision Engine | **runs normally, and the decision is recorded** |
| Intervention / replan / re-execution | **suppressed** — never executed |
| Withholding an answer (`ASK_CLARIFICATION`) | **suppressed** — the answer is returned |
| Pre-execution refusal (model router `ABSTAIN`) | **suppressed** — generation proceeds |

That last row matters: refusing before execution would destroy half the observation. Shadow Mode needs to see both what the unmanaged system *would have produced* and what ControlPlane *would have done about it*.

## Verdict Vocabulary

The bootstrap's vocabulary, derived from the Decision Engine's own `ControlAction` rather than recomputed:

| `ControlAction` | Shadow verdict |
|---|---|
| `CONTINUE` | `WOULD_CONTINUE` |
| `VERIFY` | `WOULD_VERIFY` |
| `RETRIEVE_MORE`, `CHANGE_MODEL` | `WOULD_REROUTE` |
| `REGENERATE` | `WOULD_INTERVENE` |
| `HUMAN_REVIEW` | `WOULD_ESCALATE` |
| `ASK_CLARIFICATION`, `ABSTAIN` | `WOULD_BLOCK` |

**Derived, not reimplemented.** A shadow verdict must be exactly what the enforcing system would have done. A parallel reimplementation could silently drift from the real Decision Engine, which would make shadow observations misleading in precisely the situation they are trusted for. `tests/test_shadow_mode.py::test_every_control_action_maps_to_a_verdict` asserts the mapping table stays exhaustive, so a `ControlAction` added later cannot silently be recorded as "no action".

Each shadow decision emits a `SHADOW_DECISION_RECORDED` event (severity `NOTICE` — by definition never an enforcement signal), carrying the verdict, the would-be action, and the reason.

## A Real Semantic Subtlety (found while testing)

Shadow Mode's recorded decision is the **first** decision — its judgement of the answer the unmanaged system actually produced. The enforcing runtime's *final* decision is reached after it intervened and re-evaluated, so it is a decision about a **different answer**.

The first end-to-end test written for this asserted the two were equal and failed: enforcing reached `ASK_CLARIFICATION` (after exhausting its retry budget) where shadow recorded `RETRIEVE_MORE`. The test was wrong, not the code — but the distinction is worth stating explicitly, because "shadow mode agrees with enforced mode" is the intuitive-but-incorrect way to validate this. What must hold, and what is now asserted:

- shadow mode reaches a non-`CONTINUE` decision on the same input (it saw the problem),
- the model is invoked exactly once (nothing was executed),
- the returned answer is byte-identical to the unmanaged model's answer.

## Limitations

- **Single-decision observation.** Shadow Mode records the first decision only. It does not simulate the *outcome* of the intervention it would have run (that would require executing it, which is precisely what shadow mode must not do). So it answers "would ControlPlane have acted?" but not "would that action have helped?" — the enforced runs and the ablation study answer the latter.
- **No shadow-specific persistence table.** Verdicts are carried on the event stream and derivable from the persisted decision record, following this repo's established "derive, don't duplicate" pattern (same as the Trust Layer and Permission Lineage). There is no `shadow_decisions` table.
- **Not yet measured on production-like traffic volume**, because none exists for this prototype. The measured shadow numbers currently come from the 26-case ablation dataset — `DEVELOPMENT_TEST` scale.
