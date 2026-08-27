from controlplane.context import RequestContext
from controlplane.state import ExecutionState, ExecutionStatus


def test_initial_state_is_received():
    ctx = RequestContext.new()
    state = ExecutionState.initial(ctx=ctx, query="hello")
    assert state.current_status == ExecutionStatus.RECEIVED
    assert state.current_step == "received"
    assert state.query == "hello"
    assert state.request_id == ctx.request_id
    assert state.trace_id == ctx.trace_id
    assert state.trajectory_id == ctx.trajectory_id
    assert state.errors == []
    assert state.metadata == {}
    assert state.created_at == state.updated_at


def test_advance_updates_step_status_and_timestamp():
    ctx = RequestContext.new()
    state = ExecutionState.initial(ctx=ctx, query="hello")
    created = state.created_at
    state.advance("processing", ExecutionStatus.PROCESSING)
    assert state.current_step == "processing"
    assert state.current_status == ExecutionStatus.PROCESSING
    assert state.updated_at >= created


def test_fail_records_error_and_sets_failed_status():
    ctx = RequestContext.new()
    state = ExecutionState.initial(ctx=ctx, query="hello")
    state.fail("processing", "boom")
    assert state.current_status == ExecutionStatus.FAILED
    assert state.current_step == "processing"
    assert "boom" in state.errors
