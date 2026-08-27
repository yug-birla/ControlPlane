from controlplane.context import (
    RequestContext,
    current_request_id,
    current_trace_id,
    current_trajectory_id,
    generate_request_id,
    generate_trace_id,
    generate_trajectory_id,
)


def test_id_generators_have_expected_prefixes_and_are_unique():
    assert generate_request_id().startswith("req_")
    assert generate_trace_id().startswith("trace_")
    assert generate_trajectory_id().startswith("traj_")
    assert generate_request_id() != generate_request_id()


def test_request_context_new_produces_three_distinct_ids():
    ctx = RequestContext.new()
    assert ctx.request_id != ctx.trace_id != ctx.trajectory_id
    assert ctx.request_id.startswith("req_")
    assert ctx.trace_id.startswith("trace_")
    assert ctx.trajectory_id.startswith("traj_")


def test_bind_sets_and_resets_contextvars():
    assert current_request_id() is None
    ctx = RequestContext.new()
    with ctx.bind():
        assert current_request_id() == ctx.request_id
        assert current_trace_id() == ctx.trace_id
        assert current_trajectory_id() == ctx.trajectory_id
    assert current_request_id() is None
    assert current_trace_id() is None
    assert current_trajectory_id() is None


def test_nested_bind_restores_outer_context():
    outer = RequestContext.new()
    with outer.bind():
        inner = RequestContext.new()
        with inner.bind():
            assert current_request_id() == inner.request_id
        assert current_request_id() == outer.request_id
