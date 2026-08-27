from controlplane.context import RequestContext
from controlplane.events.schema import Event, EventType, Severity
from controlplane.events.store import EventStore
from controlplane.events.transport import InProcessEventTransport
from controlplane.trajectory.store import TrajectoryStore


def test_event_create_applies_default_severity():
    ctx = RequestContext.new()
    event = Event.create(
        EventType.QUERY_RECEIVED,
        source="controlplane",
        request_id=ctx.request_id,
        trace_id=ctx.trace_id,
        trajectory_id=ctx.trajectory_id,
    )
    assert event.severity == Severity.INFO
    assert event.event_id.startswith("evt_")
    assert event.correlation_id == ctx.trace_id

    failure_event = Event.create(
        EventType.MODEL_FAILURE,
        source="model",
        request_id=ctx.request_id,
        trace_id=ctx.trace_id,
        trajectory_id=ctx.trajectory_id,
    )
    assert failure_event.severity == Severity.HIGH


def test_in_process_transport_delivers_to_all_subscribers():
    transport = InProcessEventTransport()
    received_a = []
    received_b = []
    transport.subscribe(received_a.append)
    transport.subscribe(received_b.append)

    ctx = RequestContext.new()
    event = Event.create(
        EventType.QUERY_RECEIVED,
        source="controlplane",
        request_id=ctx.request_id,
        trace_id=ctx.trace_id,
        trajectory_id=ctx.trajectory_id,
    )
    transport.publish(event)

    assert received_a == [event]
    assert received_b == [event]


def test_event_store_persists_and_retrieves_by_trajectory():
    trajectory_store = TrajectoryStore()
    ctx = RequestContext.new()
    trajectory_store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="hello")
    trajectory_store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)

    event_store = EventStore()
    event = Event.create(
        EventType.QUERY_RECEIVED,
        source="controlplane",
        request_id=ctx.request_id,
        trace_id=ctx.trace_id,
        trajectory_id=ctx.trajectory_id,
        payload={"query_preview": "hello"},
    )
    event_store.persist(event)

    events = event_store.get_by_trajectory(ctx.trajectory_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "QUERY_RECEIVED"
    assert events[0]["payload"]["query_preview"] == "hello"


def test_transport_wired_to_event_store_persists_on_publish():
    transport = InProcessEventTransport()
    event_store = EventStore()
    transport.subscribe(event_store.persist)

    trajectory_store = TrajectoryStore()
    ctx = RequestContext.new()
    trajectory_store.create_request(request_id=ctx.request_id, trace_id=ctx.trace_id, query_text="hello")
    trajectory_store.create_trajectory(trajectory_id=ctx.trajectory_id, request_id=ctx.request_id)

    event = Event.create(
        EventType.QUERY_RECEIVED,
        source="controlplane",
        request_id=ctx.request_id,
        trace_id=ctx.trace_id,
        trajectory_id=ctx.trajectory_id,
    )
    transport.publish(event)

    assert len(event_store.get_by_trajectory(ctx.trajectory_id)) == 1
