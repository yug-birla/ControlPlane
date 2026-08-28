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

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
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


class QueryProfileRecord(Base):
    """Query Fingerprint -- docs/DATA/POSTGRES_SCHEMA.md SS3.2.

    ``capability_hints`` is new this milestone (not in the original SS3.2
    field list) -- see docs/PROJECT_STATE/DECISIONS.md."""

    __tablename__ = "query_profiles"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    complexity: Mapped[str] = mapped_column(Text, nullable=False)
    sensitivity: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    actionability: Mapped[str] = mapped_column(Text, nullable=False)
    risk_vector: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    capability_hints: Mapped[dict] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ModelRegistryRecord(Base):
    """docs/DATA/POSTGRES_SCHEMA.md SS5.2, extended this milestone with
    ``source``, ``model_family``, ``parameter_count``, ``local_or_remote``,
    ``hardware_requirements``, ``license``, ``revision`` -- see
    docs/PROJECT_STATE/DECISIONS.md."""

    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    model_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    parameter_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_or_remote: Mapped[str] = mapped_column(Text, nullable=False)
    hardware_requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    license: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability_status: Mapped[str] = mapped_column(Text, nullable=False, default="AVAILABLE")
    known_strengths: Mapped[dict] = mapped_column(JSONB, default=dict)
    known_weaknesses: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ExperimentRecord(Base):
    """New this milestone -- docs/PROJECT_STATE/DECISIONS.md.
    ``docs/ALGORITHMS/*.md`` is the human-written record of *why*; these
    tables are the machine-readable record of *what was actually run and
    measured*."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    experiment_name: Mapped[str] = mapped_column(Text, nullable=False)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExperimentRunRecord(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    hardware: Mapped[dict] = mapped_column(JSONB, default=dict)
    code_commit: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvaluationResultRecord(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    experiment_run_id: Mapped[str] = mapped_column(ForeignKey("experiment_runs.id"), nullable=False)
    split: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ModelBenchmarkRecord(Base):
    __tablename__ = "model_benchmarks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    model_key: Mapped[str] = mapped_column(Text, nullable=False)
    benchmark_name: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms_p50: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    latency_ms_p95: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    latency_ms_p99: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    cold_start_ms: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    warm_latency_ms: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    throughput_qps: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    device: Mapped[str | None] = mapped_column(Text, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RouteDecisionRecord(Base):
    """New this milestone -- Capability Router + Model Router decisions,
    persisted per docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md SS59
    ("every router decision should be persisted with router_version,
    feature_schema_version, policy_version"). No hidden reasoning: every
    field here is either an enum value, a capability list, or a
    human-readable ``reason`` string built from named signals -- see
    controlplane/routing/."""

    __tablename__ = "route_decisions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    query_profile_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    capability_router_version: Mapped[str] = mapped_column(Text, nullable=False)
    selected_capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    restricted_capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    capability_reason: Mapped[str] = mapped_column(Text, nullable=False)
    execution_graph: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_router_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_action: Mapped[str] = mapped_column(Text, nullable=False)
    model_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    require_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_reason: Mapped[str] = mapped_column(Text, nullable=False)
    expected_cost_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_latency_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    """New this milestone -- incremented when a Replan creates a new
    RouteDecisionRecord for the same request after an intervention
    (controlplane/decision/, controlplane/intervention/,
    controlplane/verification/). Version 1 is always the original,
    pre-intervention route."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResponseEvaluationRecord(Base):
    """New this milestone -- per-request Evaluation layer results
    (controlplane/evaluation/evaluators.py), distinct from
    ``evaluation_results`` (aggregate experiment/benchmark metrics).
    One row per evaluator per request, including NOT_IMPLEMENTED ones,
    so the record of "what was and wasn't evaluated" is complete, not
    just the successful evaluations."""

    __tablename__ = "response_evaluations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    evaluator: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DecisionRecord(Base):
    """New this milestone -- controlplane/decision/engine.py's
    ``ControlDecision``, persisted per attempt (so a request that
    retries once has two rows: attempt_number=1 and attempt_number=2)."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    triggering_evaluator: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    can_retry: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InterventionRecord(Base):
    """New this milestone -- controlplane/intervention/engine.py's
    ``InterventionSpec``, plus ``actual_effect`` filled in by
    ``controlplane.runtime`` after the intervention actually re-executes
    (bootstrap SS35: dashboard must show "expected effect" vs. "actual
    effect")."""

    __tablename__ = "interventions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), nullable=False)
    intervention_type: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    spec: Mapped[dict] = mapped_column(JSONB, default=dict)
    expected_effect: Mapped[str] = mapped_column(Text, nullable=False)
    actual_effect: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReplanRecord(Base):
    """New this milestone -- one row per new plan version created after
    an intervention. Never overwrites/deletes the previous
    RouteDecisionRecord (``plan_version=1`` stays in the table)."""

    __tablename__ = "replans"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    from_plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VerificationRecord(Base):
    """New this milestone -- controlplane/verification/engine.py's
    ``VerificationResult``, one row per request (the final, post-retry
    verification -- not one per attempt, since verification only runs
    once the control loop reaches a terminal decision)."""

    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False)
    trajectory_id: Mapped[str] = mapped_column(ForeignKey("trajectories.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    checked_evaluators: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"
