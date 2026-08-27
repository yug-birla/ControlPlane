"""ORM models -- implement docs/DATA/POSTGRES_SCHEMA.md SS3.1 (requests),
SS9.1-9.2 (trajectories, trajectory_steps), SS10.1 (execution_ledger),
SS8.1 (event_index), plus ``model_invocations`` (new this milestone; the
conceptual "Model Invocation Record" from
docs/architecture/TRAJECTORY_AND_LEDGER.md SS13.1 never had a concrete
table before -- see docs/DATA/POSTGRES_SCHEMA.md SS10.2 for the addition).

**Deviation from the documented DDL, recorded in
docs/PROJECT_STATE/DECISIONS.md:** identifier columns are TEXT, not UUID.
Layer 1 already decided identifiers are prefixed strings
(``req_<uuid4>``, ``trace_<uuid4>``, ``traj_<uuid4>``) for log
readability; a native Postgres UUID column cannot hold that prefix.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RequestRecord(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    application_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrajectoryRecord(Base):
    __tablename__ = "trajectories"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trajectory_type: Mapped[str] = mapped_column(Text, nullable=False, default="SINGLE_REQUEST")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_status: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrajectoryStepRecord(Base):
    __tablename__ = "trajectory_steps"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, default="SYSTEM")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_ref: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_ref: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionLedgerRecord(Base):
    """Append-only. Application code must never UPDATE or DELETE a row here."""

    __tablename__ = "execution_ledger"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    consequence_class: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[dict] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class EventRecord(Base):
    __tablename__ = "event_index"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_version: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    persisted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class ModelInvocationRecord(Base):
    """New table this milestone -- see docs/DATA/POSTGRES_SCHEMA.md SS10.2."""

    __tablename__ = "model_invocations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"
