# Dynamic Planning and Capability Discovery

**Status:** IMPLEMENTED (Milestone 10).
**Code:** `controlplane/capabilities/registry.py`, `controlplane/planning/replanner.py`, wired in `controlplane/runtime.py::_attempt_capability_replan`.
**Tests:** `tests/test_replanner.py` (10), `tests/test_control_loop_scenarios.py` (3 end-to-end).

## The Problem

Through Milestone 9, a "replan" did this:

1. bump `plan_version`
2. emit `REPLAN_TRIGGERED`
3. re-run the **existing** RAG node with a wider `k`

The execution graph itself never changed. No node was ever added, removed, or replaced. The system recorded plan *versions* while executing a *fixed* workflow — exactly what the architecture spec warns against: *"Do not keep one fixed graph while pretending planning is dynamic."*

## What Changed

On insufficient evidence, ControlPlane now consults a **Capability Registry** for a capability that serves a data requirement of *this query* which nothing in the current plan serves — and if one exists, **adds it to the graph** and rewires the merge node to consume it.

```
PLAN V1                          PLAN V2
data_rag                         data_rag
   ↓                             data_sql          ← added
merge (deps: data_rag)           merge (deps: data_rag, data_sql)   ← rewired
   ↓                                ↓
generation                       generation
```

Verified end-to-end, not asserted — the graph above is the real persisted final plan for a query needing both document and structured evidence.

## Capability Registry (`controlplane/capabilities/registry.py`)

Before this, capability knowledge was scattered across four places: the `CapabilityHint` enum, a hard-coded `_DATA_CAPABILITIES` set in the router, a handler dict in the runtime, and policy restriction lists. Nothing could answer *"what capabilities exist, and which could supply the evidence this query still needs?"* — which is the prerequisite for discovery-driven planning.

Each descriptor carries: `capability_id`, description, `status`, `side_effect_level`, `supplies_evidence`, `satisfies_data_requirements`, `required_permissions`, and latency/cost/risk classes.

**Status is never more optimistic than reality.** `CHAT_HISTORY`, `MEMORY`, and `WEB` are registered as `MOCKED` because they run via the executor's placeholder handler. A registry that claimed they worked would make the planner select one and then silently produce no evidence. `discover()` excludes them from evidence searches by default while still making their existence visible.

**Boundary:** the registry describes *how to reach* a capability and *what it can do*. ControlPlane still decides *whether, when, and which*. Nothing in the module makes a control decision. This is the same boundary MCP must respect.

## Why This Is Not Hard-Coded

The spec is explicit: *"Do NOT hard-code: RAG FAILURE → ALWAYS SQL."*

Selection is a lookup, not a rule:

1. Compute which of the query's **own measured** `data_requirement` values are unserved by nodes already in the plan.
2. Ask the registry which `AVAILABLE`, evidence-supplying, policy-permitted capabilities satisfy those requirements.
3. Prefer the cheapest/fastest.

Consequences that fall out of this rather than being special-cased:

- A document-only question whose `RAG_CORPUS` requirement is already served gets **no** new node — the replanner declines and the system falls back to widening retrieval.
- A policy-restricted capability is never proposed.
- A `MOCKED` capability is never proposed as an evidence source.
- A query with no declared data requirement gets no new node.

Each of these is a test in `tests/test_replanner.py`.

## Insufficient ≠ Conflicting (a real regression)

The first implementation applied the capability-adding replan to **every** `RETRIEVE_MORE` intervention. That broke the Milestone 6 conflicting-evidence scenario, and the failure was correct:

**Adding a new data source cannot resolve a contradiction between two sources that already disagree** — it supplies a third opinion. The architecture's answer to conflicting evidence is to widen retrieval looking for an *authoritative* source, then disclose the conflict rather than pick a side.

The replan is now skipped when any evaluator reports `CONFLICTING`, and both directions are regression-tested (`test_conflicting_evidence_does_not_trigger_a_capability_adding_replan_regression`).

This distinction was found by an existing test failing, not by design foresight — the same "real end-to-end scenarios catch integration errors that unit tests miss" pattern as Milestones 5, 7, and 9.

## Failure Handling

- A capability the registry offers but the runtime has **no live handler** for → node marked `SKIPPED` with an explicit error, and the caller falls back to widening retrieval. Never left `PENDING` pretending it contributed.
- A new capability node that **throws** → marked `FAILED`, logged, fall back. A newly added capability failing must not fail the whole request.
- `graph.validate()` runs after every mutation, so a cycle or dangling dependency fails loudly at replan time rather than during execution.

## Limitations

- **Only additive.** `ADD_NODE` is implemented; `REMOVE_NODE`, `REPLACE_NODE`, `CHANGE_ORDER`, `PARALLELIZE`/`SERIALIZE` from the spec's mutation vocabulary are not. Additive replanning is the case the evidence-insufficiency path actually needs; the others have no measured trigger yet.
- **One replan per request in practice**, bounded by the Decision Engine's existing `max_attempts` and the control loop's independent hard iteration cap.
- **Registry is static in-process metadata**, not populated by MCP discovery. It is deliberately shaped so an MCP fabric can populate it later (`provider` field already distinguishes `internal` from an MCP server id) rather than replacing it.
- **The added node executes directly**, not through the graph executor's wave scheduler, so a replan-added capability does not currently run in parallel with anything. Correct but not optimal.
