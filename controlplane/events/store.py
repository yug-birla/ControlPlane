"""Durable event history -- docs/DATA/POSTGRES_SCHEMA.md SS8.1 (event_index).

This is the persistence side of the event contract, kept separate from
``EventTransport`` (controlplane/events/transport.py): the transport
delivers an event to consumers; this store is one such consumer, the one
responsible for durable history so the event history can be reconstructed
later (EVENT_MODEL.md SS14).
"""

from __future__ import annotations

from controlplane.db.engine import session_scope
from controlplane.db.models import EventRecord
from controlplane.events.schema import Event


class EventStore:
    def persist(self, event: Event) -> None:
        with session_scope() as session:
            session.add(
                EventRecord(
                    id=event.event_id,
                    event_type=event.event_type.value,
                    event_version=event.event_version,
                    request_id=event.request_id,
                    trace_id=event.trace_id,
                    trajectory_id=event.trajectory_id,
                    source_type=event.source,
                    severity=event.severity.value,
                    observed_at=event.timestamp,
                    correlation_id=event.correlation_id,
                    payload=event.payload,
                )
            )

    def get_by_trajectory(self, trajectory_id: str) -> list[dict]:
        from sqlalchemy import select

        with session_scope() as session:
            rows = session.execute(
                select(EventRecord)
                .where(EventRecord.trajectory_id == trajectory_id)
                .order_by(EventRecord.observed_at)
            ).scalars()
            return [
                {
                    "event_id": r.id,
                    "event_type": r.event_type,
                    "observed_at": r.observed_at,
                    "severity": r.severity,
                    "source": r.source_type,
                    "payload": r.payload,
                }
                for r in rows
            ]
