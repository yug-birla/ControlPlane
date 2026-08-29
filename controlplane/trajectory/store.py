"""Trajectory Store -- reconstructable execution state/history.

docs/architecture/TRAJECTORY_AND_LEDGER.md: "Trajectory Store =
reconstructable execution state/history" (distinct from the Execution
Ledger, which is append-only consequential facts -- see
controlplane/ledger/ledger.py). Backed by Postgres
(``requests``/``trajectories``/``trajectory_steps`` -- see
controlplane/db/models.py).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

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
        duration_ms: float | None = None,
    ) -> str:
        """``duration_ms`` is how long the component ACTUALLY took,
        measured by the caller with a monotonic clock.

        WHY THIS PARAMETER EXISTS. Steps are recorded after the work
        finishes, in one call. ``started_at`` therefore defaulted to
        flush time while ``completed_at`` was set moments earlier in
        Python -- so every span came out as zero or, in 298 of 400
        sampled steps, NEGATIVE (one step recorded a completion 1ms
        before its own start). The consequence was silent: every
        component reported ``latency_ms_p50: null`` in the health view,
        and the latency field the diagnostics spec requires was never
        actually populated. The view looked fine; it was measuring
        nothing.

        A duration cannot be reconstructed after the fact, so the caller
        has to supply it. ``started_at`` is then back-dated from the real
        completion time by the real measured duration, which keeps the
        schema unchanged and makes ``completed_at - started_at`` mean
        what every reader already assumes it means."""
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
                finished = _utcnow()
                step.completed_at = finished
                if duration_ms is not None:
                    step.started_at = finished - timedelta(milliseconds=max(duration_ms, 0.0))
                else:
                    # No measurement supplied: record a zero-width span
                    # explicitly rather than letting the column default
                    # produce a negative one. An unmeasured component
                    # must look unmeasured, not fast.
                    step.started_at = finished
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
