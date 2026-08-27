"""Execution Ledger -- append-only record of consequential execution facts.

docs/architecture/TRAJECTORY_AND_LEDGER.md: "Execution Ledger =
append-only consequential facts" (distinct from the Trajectory Store --
see controlplane/trajectory/store.py). Rows are never updated or deleted
by application code (docs/DATA/POSTGRES_SCHEMA.md SS10.1: "Do not update
old ledger records. If a correction is required, append a compensating
record.").

``action_type`` examples are the ones already documented in
POSTGRES_SCHEMA.md SS10.1 (``MODEL_INVOKED``, ``DOCUMENT_ACCESSED``, ...).
``consequence_class`` uses the External Side-Effect classification from
CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS30
(``READ_ONLY``/``REVERSIBLE_WRITE``/``IRREVERSIBLE_WRITE``/``HIGH_IMPACT_ACTION``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import func, select

from controlplane.db.engine import session_scope
from controlplane.db.models import ExecutionLedgerRecord, new_id


class ConsequenceClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    IRREVERSIBLE_WRITE = "IRREVERSIBLE_WRITE"
    HIGH_IMPACT_ACTION = "HIGH_IMPACT_ACTION"


class ExecutionLedger:
    def append(
        self,
        *,
        trajectory_id: str,
        actor_type: str,
        actor_id: str,
        action_type: str,
        consequence_class: ConsequenceClass,
        resource_type: str | None = None,
        resource_id: str | None = None,
        evidence_refs: dict | None = None,
        metadata: dict | None = None,
    ) -> str:
        with session_scope() as session:
            next_seq = session.execute(
                select(func.coalesce(func.max(ExecutionLedgerRecord.sequence_number), 0)).where(
                    ExecutionLedgerRecord.trajectory_id == trajectory_id
                )
            ).scalar_one()
            entry_id = new_id("ledger")
            session.add(
                ExecutionLedgerRecord(
                    id=entry_id,
                    trajectory_id=trajectory_id,
                    sequence_number=next_seq + 1,
                    occurred_at=datetime.now(timezone.utc),
                    actor_type=actor_type,
                    actor_id=actor_id,
                    action_type=action_type,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    consequence_class=consequence_class.value,
                    evidence_refs=evidence_refs or {},
                    metadata_=metadata or {},
                )
            )
            return entry_id

    def get_by_trajectory(self, trajectory_id: str) -> list[dict]:
        with session_scope() as session:
            rows = session.execute(
                select(ExecutionLedgerRecord)
                .where(ExecutionLedgerRecord.trajectory_id == trajectory_id)
                .order_by(ExecutionLedgerRecord.sequence_number)
            ).scalars()
            return [
                {
                    "id": r.id,
                    "sequence_number": r.sequence_number,
                    "occurred_at": r.occurred_at,
                    "actor_type": r.actor_type,
                    "actor_id": r.actor_id,
                    "action_type": r.action_type,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "consequence_class": r.consequence_class,
                    "evidence_refs": r.evidence_refs,
                    "metadata": r.metadata_,
                }
                for r in rows
            ]
