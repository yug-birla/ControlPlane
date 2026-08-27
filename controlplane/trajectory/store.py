"""Trajectory Store -- reconstructable execution state/history.

docs/architecture/TRAJECTORY_AND_LEDGER.md: "Trajectory Store =
reconstructable execution state/history" (distinct from the Execution
Ledger, which is append-only consequential facts -- see
controlplane/ledger/ledger.py). Backed by Postgres
(``requests``/``trajectories``/``trajectory_steps`` -- see
controlplane/db/models.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from controlplane.db.engine import session_scope
from controlplane.db.models import RequestRecord, TrajectoryRecord, TrajectoryStepRecord, new_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrajectoryStore:
    def create_request(
        self, *, request_id: str, trace_id: str, query_text: str, application_id: str | None = None
    ) -> None:
        with session_scope() as session:
            session.add(
                RequestRecord(
                    id=request_id,
                    trace_id=trace_id,
                    application_id=application_id,
                    query_text=query_text,
                    status="RECEIVED",
                )
            )

    def update_request_status(self, request_id: str, status: str, completed: bool = False) -> None:
        with session_scope() as session:
            record = session.get(RequestRecord, request_id)
            if record is None:
                raise LookupError(f"unknown request_id: {request_id}")
            record.status = status
            record.updated_at = _utcnow()
            if completed:
                record.completed_at = _utcnow()

    def create_trajectory(
        self, *, trajectory_id: str, request_id: str, trajectory_type: str = "SINGLE_REQUEST"
    ) -> None:
        with session_scope() as session:
            session.add(
                TrajectoryRecord(
                    id=trajectory_id,
                    request_id=request_id,
                    trajectory_type=trajectory_type,
                    status="RECEIVED",
                )
            )

    def update_trajectory_status(
        self, trajectory_id: str, status: str, final_status: str | None = None, completed: bool = False
    ) -> None:
        with session_scope() as session:
            record = session.get(TrajectoryRecord, trajectory_id)
            if record is None:
                raise LookupError(f"unknown trajectory_id: {trajectory_id}")
            record.status = status
            if final_status is not None:
                record.final_status = final_status
            if completed:
                record.completed_at = _utcnow()

    def append_step(
        self,
        *,
        trajectory_id: str,
        step_type: str,
        status: str,
        input_ref: dict | None = None,
        output_ref: dict | None = None,
        actor_type: str = "SYSTEM",
        completed: bool = False,
    ) -> str:
        with session_scope() as session:
            next_seq = session.execute(
                select(func.coalesce(func.max(TrajectoryStepRecord.sequence_number), 0)).where(
                    TrajectoryStepRecord.trajectory_id == trajectory_id
                )
            ).scalar_one()
            step_id = new_id("step")
            step = TrajectoryStepRecord(
                id=step_id,
                trajectory_id=trajectory_id,
                sequence_number=next_seq + 1,
                step_type=step_type,
                actor_type=actor_type,
                status=status,
                input_ref=input_ref or {},
                output_ref=output_ref or {},
            )
            if completed:
                step.completed_at = _utcnow()
            session.add(step)
            return step_id

    def update_step_status(
        self, step_id: str, status: str, output_ref: dict | None = None, completed: bool = False
    ) -> None:
        with session_scope() as session:
            record = session.get(TrajectoryStepRecord, step_id)
            if record is None:
                raise LookupError(f"unknown step_id: {step_id}")
            record.status = status
            if output_ref is not None:
                record.output_ref = output_ref
            if completed:
                record.completed_at = _utcnow()

    def get_history(self, trajectory_id: str) -> list[dict]:
        with session_scope() as session:
            rows = session.execute(
                select(TrajectoryStepRecord)
                .where(TrajectoryStepRecord.trajectory_id == trajectory_id)
                .order_by(TrajectoryStepRecord.sequence_number)
            ).scalars()
            return [
                {
                    "sequence_number": r.sequence_number,
                    "step_type": r.step_type,
                    "status": r.status,
                    "input_ref": r.input_ref,
                    "output_ref": r.output_ref,
                    "started_at": r.started_at,
                    "completed_at": r.completed_at,
                }
                for r in rows
            ]

    def get_trajectory(self, trajectory_id: str) -> dict | None:
        with session_scope() as session:
            record = session.get(TrajectoryRecord, trajectory_id)
            if record is None:
                return None
            return {
                "id": record.id,
                "request_id": record.request_id,
                "trajectory_type": record.trajectory_type,
                "status": record.status,
                "started_at": record.started_at,
                "completed_at": record.completed_at,
                "final_status": record.final_status,
            }
