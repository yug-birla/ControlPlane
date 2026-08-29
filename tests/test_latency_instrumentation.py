"""Regression tests for component-level latency recording.

THE DEFECT THESE PIN. Trajectory steps are written after the work
finishes, in a single call. ``completed_at`` was set in Python moments
before flush while ``started_at`` came from a column default evaluated
AT flush -- so spans came out zero or negative (one sampled step
recorded a completion 1ms before its own start; 298 of 400 sampled steps
had non-positive elapsed time). Every component consequently reported
``latency_ms_p50: null`` in the component-health view.

Nothing failed. No test broke. The view rendered, the column existed,
and the number it displayed was null forever. That is precisely the
class of defect a passing suite hides, so these tests assert on the
recorded VALUE rather than on the code path.
"""

# Every synthetic span below uses a ``test_span_*`` step type rather
# than a real component name. These tests write to the same development
# database the dashboard reads, and an injected 5000ms "routing" span
# would silently corrupt the component-health percentiles a human is
# meant to trust.

from __future__ import annotations

from datetime import timedelta

from controlplane.db.engine import session_scope
from controlplane.db.models import TrajectoryStepRecord
from controlplane.trajectory.store import TrajectoryStore


def _step(**kwargs) -> TrajectoryStepRecord:
    store = TrajectoryStore()
    trajectory_id = kwargs.pop("trajectory_id")
    step_id = store.append_step(trajectory_id=trajectory_id, status="COMPLETED", completed=True, **kwargs)
    with session_scope() as session:
        record = session.get(TrajectoryStepRecord, step_id)
        session.expunge(record)
    return record


def _new_trajectory() -> str:
    from controlplane.context import RequestContext

    ctx = RequestContext.new()
    store = TrajectoryStore()
    with ctx.bind():
        store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="latency instrumentation test")
        store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)
    return ctx.trajectory_id


def test_a_measured_duration_is_recorded_as_a_real_span():
    record = _step(trajectory_id=_new_trajectory(), step_type="test_span_measured", duration_ms=250.0)
    elapsed = (record.completed_at - record.started_at).total_seconds() * 1000
    assert 249.0 <= elapsed <= 251.0, elapsed


def test_a_span_is_never_negative_regression():
    """The exact observed corruption: completed_at earlier than
    started_at, which made every downstream percentile null."""
    for duration in (0.0, 1.0, 5000.0, None):
        record = _step(trajectory_id=_new_trajectory(), step_type="test_span_negative_guard", duration_ms=duration)
        assert record.completed_at >= record.started_at, (duration, record.started_at, record.completed_at)


def test_an_unmeasured_component_looks_unmeasured_rather_than_instant():
    """Honesty guard. When no duration is supplied the span is exactly
    zero, not a small positive number -- an unmeasured component must
    not be reportable as a fast one."""
    record = _step(trajectory_id=_new_trajectory(), step_type="test_span_unmeasured", duration_ms=None)
    assert record.completed_at == record.started_at


def test_negative_durations_cannot_corrupt_a_span():
    record = _step(trajectory_id=_new_trajectory(), step_type="test_span_negative_input", duration_ms=-42.0)
    assert record.completed_at >= record.started_at


def test_component_health_reports_a_real_percentile_once_durations_exist():
    """End-to-end guard on the actual dashboard aggregate: if latency
    recording regresses, this is what a human would see go blank."""
    trajectory_id = _new_trajectory()
    for _ in range(3):
        _step(trajectory_id=trajectory_id, step_type="test_span_health", duration_ms=120.0)

    from controlplane.dashboard.queries import aggregate_component_health

    health = aggregate_component_health(limit=50)
    component = next((c for c in health["components"] if c["component"] == "test_span_health"), None)
    assert component is not None, "component missing from health view"
    assert component["latency_ms_p50"] is not None, "latency percentile is null again"
    assert component["latency_ms_p50"] > 0


def test_graph_node_latency_is_measured_with_a_monotonic_clock():
    """The capability nodes already had a real measurement; it simply
    never reached the trajectory. This pins the source of truth."""
    from controlplane.execution.graph import ExecutionNode

    node = ExecutionNode(node_id="data_rag", capability="RAG")
    assert node.latency_ms is None, "an unrun node must not claim a latency"
    node.started_at = 100.0
    node.completed_at = 100.75
    assert abs(node.latency_ms - 750.0) < 1e-6


def test_prompt_evidence_cap_limits_what_the_model_sees_only():
    """The cap must shrink the PROMPT without touching the retrieved
    evidence that adequacy and grounding are judged on."""
    from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus
    from controlplane.runtime import Runtime

    node = ExecutionNode(node_id="data_rag", capability="RAG")
    node.status = NodeStatus.COMPLETED
    node.output_ref = {"evidence": [{"document": f"DOC{i}", "text": f"chunk {i}"} for i in range(5)]}
    graph = ExecutionGraph([node])

    full = Runtime._build_generation_prompt("q", graph)
    capped = Runtime._build_generation_prompt("q", graph, prompt_evidence_k=2)

    assert full.count("chunk ") == 5
    assert capped.count("chunk ") == 2
    assert "chunk 0" in capped and "chunk 4" not in capped  # reranked order preserved
    assert len(node.output_ref["evidence"]) == 5, "capping the prompt must not mutate the evidence"
