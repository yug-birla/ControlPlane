"""End-to-end integration tests: API -> Runtime -> Trajectory Store ->
Execution Ledger -> Event Model -> Postgres, with a fake model provider
(no live external API in automated tests -- see tests/manual_groq_live_check.py).

Requires the ControlPlane Postgres container (docker compose up -d postgres).
"""

from fastapi.testclient import TestClient

import controlplane.api.routes as routes_module
from controlplane.events.store import EventStore
from controlplane.ledger.ledger import ExecutionLedger
from controlplane.main import app
from controlplane.trajectory.store import TrajectoryStore
from tests.fakes import FailingModelProvider, FakeModelProvider

client = TestClient(app)


def test_full_flow_persists_trajectory_ledger_and_events(monkeypatch):
    provider = FakeModelProvider(content="Paris is the capital of France.")
    monkeypatch.setattr(routes_module._runtime, "_provider_factory", lambda settings: provider)

    resp = client.post("/v1/requests", json={"query": "What is the capital of France?"})
    assert resp.status_code == 200
    body = resp.json()
    trajectory_id = body["trajectory_id"]

    # 1. Trajectory persisted, reachable via a brand-new store instance
    #    (i.e. not relying on any in-process object -- only the DB).
    trajectory = TrajectoryStore().get_trajectory(trajectory_id)
    assert trajectory is not None
    assert trajectory["status"] == "COMPLETED"
    assert trajectory["final_status"] == "COMPLETED"

    history = TrajectoryStore().get_history(trajectory_id)
    assert [h["step_type"] for h in history] == ["received", "model_invocation", "completed"]
    assert all(h["status"] in ("COMPLETED",) for h in history)

    # 2. Ledger has exactly one MODEL_INVOKED entry for this trajectory.
    ledger_entries = ExecutionLedger().get_by_trajectory(trajectory_id)
    assert len(ledger_entries) == 1
    assert ledger_entries[0]["action_type"] == "MODEL_INVOKED"
    assert ledger_entries[0]["consequence_class"] == "READ_ONLY"
    assert ledger_entries[0]["metadata"]["status"] == "SUCCESS"

    # 3. Events recorded in order: QUERY_RECEIVED, MODEL_CALLED, FINAL_RESPONSE_GENERATED.
    events = EventStore().get_by_trajectory(trajectory_id)
    assert [e["event_type"] for e in events] == [
        "QUERY_RECEIVED",
        "MODEL_CALLED",
        "FINAL_RESPONSE_GENERATED",
    ]

    # 4. The response answer matches what the model produced.
    assert body["answer"] == "Paris is the capital of France."


def test_failed_model_invocation_still_persists_trajectory_and_ledger(monkeypatch):
    monkeypatch.setattr(
        routes_module._runtime, "_provider_factory", lambda settings: FailingModelProvider()
    )
    quiet_client = TestClient(app, raise_server_exceptions=False)
    resp = quiet_client.post("/v1/requests", json={"query": "trigger a failure"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error_code"] == "DEPENDENCY_ERROR"
    assert body["retryable"] is True
    assert body["request_id"] is not None
    assert body["trace_id"] is not None

    # The trajectory_id isn't in the error body by design (it's an
    # execution-internal detail, not part of the public error contract),
    # so recover it via the request_id -> trajectory relationship instead.
    trajectory = _trajectory_for_request(body["request_id"])
    assert trajectory is not None
    assert trajectory["status"] == "FAILED"
    assert trajectory["final_status"] == "FAILED"

    ledger_entries = ExecutionLedger().get_by_trajectory(trajectory["id"])
    assert len(ledger_entries) == 1
    assert ledger_entries[0]["metadata"]["status"] == "FAILURE"

    events = EventStore().get_by_trajectory(trajectory["id"])
    assert [e["event_type"] for e in events] == ["QUERY_RECEIVED", "MODEL_FAILURE"]


def _trajectory_for_request(request_id: str) -> dict | None:
    from sqlalchemy import select

    from controlplane.db.engine import session_scope
    from controlplane.db.models import TrajectoryRecord

    with session_scope() as session:
        record = session.execute(
            select(TrajectoryRecord).where(TrajectoryRecord.request_id == request_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        return {"id": record.id, "status": record.status, "final_status": record.final_status}
