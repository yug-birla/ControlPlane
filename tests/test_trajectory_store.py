"""Requires the ControlPlane Postgres container (docker compose up -d postgres)."""

from controlplane.context import RequestContext
from controlplane.trajectory.store import TrajectoryStore


def test_create_and_retrieve_trajectory():
    store = TrajectoryStore()
    ctx = RequestContext.new()

    store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="hello")
    store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)

    trajectory = store.get_trajectory(ctx.trajectory_id)
    assert trajectory is not None
    assert trajectory["id"] == ctx.trajectory_id
    assert trajectory["request_id"] == ctx.request_id
    assert trajectory["status"] == "RECEIVED"
    assert trajectory["completed_at"] is None


def test_unknown_trajectory_returns_none():
    store = TrajectoryStore()
    assert store.get_trajectory("traj_does-not-exist") is None


def test_update_trajectory_status_and_completion():
    store = TrajectoryStore()
    ctx = RequestContext.new()
    store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="hello")
    store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)

    store.update_trajectory_status(ctx.trajectory_id, "COMPLETED", final_status="COMPLETED", completed=True)

    trajectory = store.get_trajectory(ctx.trajectory_id)
    assert trajectory["status"] == "COMPLETED"
    assert trajectory["final_status"] == "COMPLETED"
    assert trajectory["completed_at"] is not None


def test_append_step_assigns_increasing_sequence_numbers():
    store = TrajectoryStore()
    ctx = RequestContext.new()
    store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="hello")
    store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)

    store.append_step(trajectory_id=ctx.trajectory_id, step_type="received", status="COMPLETED", completed=True)
    store.append_step(trajectory_id=ctx.trajectory_id, step_type="model_invocation", status="RUNNING")
    store.append_step(trajectory_id=ctx.trajectory_id, step_type="completed", status="COMPLETED", completed=True)

    history = store.get_history(ctx.trajectory_id)
    assert [h["sequence_number"] for h in history] == [1, 2, 3]
    assert [h["step_type"] for h in history] == ["received", "model_invocation", "completed"]


def test_history_is_chronological_and_scoped_to_one_trajectory():
    store = TrajectoryStore()
    ctx_a = RequestContext.new()
    ctx_b = RequestContext.new()
    for ctx in (ctx_a, ctx_b):
        store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="hello")
        store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)
        store.append_step(trajectory_id=ctx.trajectory_id, step_type="received", status="COMPLETED")

    history_a = store.get_history(ctx_a.trajectory_id)
    assert len(history_a) == 1
