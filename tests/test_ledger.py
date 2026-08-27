"""Requires the ControlPlane Postgres container (docker compose up -d postgres)."""

from controlplane.context import RequestContext
from controlplane.ledger.ledger import ConsequenceClass, ExecutionLedger
from controlplane.trajectory.store import TrajectoryStore


def _new_trajectory():
    store = TrajectoryStore()
    ctx = RequestContext.new()
    store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="hello")
    store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)
    return ctx


def test_append_and_retrieve_ledger_entry():
    ctx = _new_trajectory()
    ledger = ExecutionLedger()

    entry_id = ledger.append(
        trajectory_id=ctx.trajectory_id,
        actor_type="SYSTEM",
        actor_id="controlplane-runtime",
        action_type="MODEL_INVOKED",
        consequence_class=ConsequenceClass.READ_ONLY,
        resource_type="model",
        resource_id="fake-model-1",
        metadata={"status": "SUCCESS"},
    )

    entries = ledger.get_by_trajectory(ctx.trajectory_id)
    assert len(entries) == 1
    assert entries[0]["id"] == entry_id
    assert entries[0]["action_type"] == "MODEL_INVOKED"
    assert entries[0]["consequence_class"] == "READ_ONLY"
    assert entries[0]["metadata"]["status"] == "SUCCESS"
    assert entries[0]["sequence_number"] == 1


def test_ledger_sequence_numbers_increase_monotonically():
    ctx = _new_trajectory()
    ledger = ExecutionLedger()
    for _ in range(3):
        ledger.append(
            trajectory_id=ctx.trajectory_id,
            actor_type="SYSTEM",
            actor_id="controlplane-runtime",
            action_type="MODEL_INVOKED",
            consequence_class=ConsequenceClass.READ_ONLY,
        )
    entries = ledger.get_by_trajectory(ctx.trajectory_id)
    assert [e["sequence_number"] for e in entries] == [1, 2, 3]


def test_ledger_is_scoped_per_trajectory():
    ctx_a = _new_trajectory()
    ctx_b = _new_trajectory()
    ledger = ExecutionLedger()
    ledger.append(
        trajectory_id=ctx_a.trajectory_id,
        actor_type="SYSTEM",
        actor_id="x",
        action_type="MODEL_INVOKED",
        consequence_class=ConsequenceClass.READ_ONLY,
    )
    assert len(ledger.get_by_trajectory(ctx_a.trajectory_id)) == 1
    assert len(ledger.get_by_trajectory(ctx_b.trajectory_id)) == 0
