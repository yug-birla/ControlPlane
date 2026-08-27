"""Traceable runtime -- Milestone 2.

USER QUERY -> create request/trajectory -> QUERY_RECEIVED -> Query
Profiler -> QUERY_PROFILED -> Risk Profiler + Policy -> RISK_DETECTED ->
invoke the configured model provider -> MODEL_CALLED/MODEL_FAILURE ->
model invocation record -> ledger entry -> FINAL_RESPONSE_GENERATED ->
update trajectory -> structured response.

Still no capability/model routing, RAG, evaluation, intervention, or
replanning -- the query profile and risk assessment are computed and
persisted, but every query still goes to the one configured model
regardless of what they say (route hints are informational only this
milestone). See docs/PROJECT_STATE/FUTURE_WORK.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from controlplane.config import Settings, get_settings
from controlplane.context import RequestContext
from controlplane.db.models import new_id
from controlplane.errors import ConfigurationError, ControlPlaneError, DependencyError, TimeoutError
from controlplane.events.schema import Event, EventType, Severity
from controlplane.events.store import EventStore
from controlplane.events.transport import EventTransport, InProcessEventTransport
from controlplane.ledger.ledger import ConsequenceClass, ExecutionLedger
from controlplane.logging_config import get_logger
from controlplane.models.provider import ModelProviderError, ModelProviderTimeout
from controlplane.models.registry import get_configured_provider
from controlplane.policy.baseline import PolicyBaseline
from controlplane.query_intelligence.fingerprint import QueryFingerprint
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import RiskProfile, RiskSeverity
from controlplane.state import ExecutionState, ExecutionStatus
from controlplane.trajectory.store import TrajectoryStore

logger = get_logger("controlplane.runtime")

_QUERY_PREVIEW_LEN = 200

_RISK_TO_EVENT_SEVERITY = {
    RiskSeverity.NO_ACTION: Severity.INFO,
    RiskSeverity.LOW_RISK: Severity.NOTICE,
    RiskSeverity.MEDIUM_RISK: Severity.WARNING,
    RiskSeverity.HIGH_RISK: Severity.HIGH,
    RiskSeverity.CRITICAL: Severity.CRITICAL,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Runtime:
    def __init__(
        self,
        trajectory_store: TrajectoryStore,
        ledger: ExecutionLedger,
        event_transport: EventTransport,
        settings_provider=get_settings,
        provider_factory=get_configured_provider,
        query_profiler=None,
        risk_profiler=None,
        policy=None,
    ) -> None:
        self._trajectory_store = trajectory_store
        self._ledger = ledger
        self._events = event_transport
        self._settings_provider = settings_provider
        self._provider_factory = provider_factory
        self._query_profiler = query_profiler or HybridQueryProfiler()
        self._risk_profiler = risk_profiler or BaselineRiskProfiler()
        self._policy = policy or PolicyBaseline()

    def _publish(
        self, event_type: EventType, ctx: RequestContext, *, source: str, payload: dict, severity: Severity | None = None
    ) -> None:
        event = Event.create(
            event_type,
            source=source,
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            trajectory_id=ctx.trajectory_id,
            payload=payload,
            severity=severity,
        )
        self._events.publish(event)

    def handle(self, ctx: RequestContext, state: ExecutionState) -> ExecutionState:
        from sqlalchemy.exc import SQLAlchemyError

        query = state.query
        settings = self._settings_provider()

        try:
            self._trajectory_store.create_request(
                request_id=ctx.request_id, trace_id=ctx.trace_id, query_text=query
            )
            self._trajectory_store.create_trajectory(
                trajectory_id=ctx.trajectory_id, request_id=ctx.request_id
            )
            self._trajectory_store.append_step(
                trajectory_id=ctx.trajectory_id,
                step_type="received",
                status="COMPLETED",
                input_ref={"query": query},
                completed=True,
            )
        except SQLAlchemyError as exc:
            logger.error("storage_failure", extra={"cp_fields": {"step": "received"}})
            raise DependencyError("storage is unavailable") from exc

        self._publish(
            EventType.QUERY_RECEIVED,
            ctx,
            source="controlplane",
            payload={"query_preview": query[:_QUERY_PREVIEW_LEN]},
        )

        try:
            fingerprint, risk = self._profile_and_assess_risk(ctx, query)
        except ControlPlaneError as exc:
            self._fail(ctx, state, step_id=None, error=exc)
            raise
        policy_decision = self._policy.decide(risk.severity)
        state.metadata["query_profile"] = fingerprint.model_dump(mode="json")
        state.metadata["risk"] = risk.model_dump(mode="json")
        state.metadata["policy"] = policy_decision.model_dump(mode="json")

        state.advance("model_invocation", ExecutionStatus.PROCESSING)
        self._trajectory_store.update_trajectory_status(ctx.trajectory_id, "PROCESSING")
        step_id = self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="model_invocation",
            status="RUNNING",
            input_ref={"query_preview": query[:_QUERY_PREVIEW_LEN]},
        )

        try:
            result = self._invoke_model(ctx, settings, query)
        except ControlPlaneError as exc:
            self._fail(ctx, state, step_id=step_id, error=exc)
            raise

        self._trajectory_store.update_step_status(
            step_id,
            "COMPLETED",
            output_ref={"model_invocation_id": result["invocation_id"]},
            completed=True,
        )

        state.metadata["answer"] = result["content"]
        state.metadata["model"] = {
            "provider": result["provider"],
            "model": result["model"],
            "latency_ms": result["latency_ms"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        }

        self._publish(
            EventType.FINAL_RESPONSE_GENERATED,
            ctx,
            source="controlplane",
            payload={"model_invocation_id": result["invocation_id"]},
        )
        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="completed",
            status="COMPLETED",
            output_ref={"model_invocation_id": result["invocation_id"]},
            completed=True,
        )
        self._trajectory_store.update_trajectory_status(
            ctx.trajectory_id, "COMPLETED", final_status="COMPLETED", completed=True
        )
        self._trajectory_store.update_request_status(ctx.request_id, "COMPLETED", completed=True)

        state.advance("completed", ExecutionStatus.COMPLETED)
        return state

    def _profile_and_assess_risk(self, ctx: RequestContext, query: str) -> tuple[QueryFingerprint, RiskProfile]:
        from controlplane.db.engine import session_scope
        from controlplane.db.models import QueryProfileRecord
        from controlplane.models.embedding_provider import EmbeddingProviderError

        try:
            fingerprint = self._query_profiler.profile(query)
        except EmbeddingProviderError as exc:
            # Offline-first (bootstrap SS14): if the local model isn't
            # cached, fail clearly rather than silently falling back to a
            # remote model the policy may not permit for this task.
            logger.error("local_model_unavailable", extra={"cp_fields": {"error": str(exc)}})
            raise ConfigurationError(f"local embedding model unavailable: {exc}") from exc
        profile_id = new_id("qp")
        with session_scope() as session:
            session.add(
                QueryProfileRecord(
                    id=profile_id,
                    request_id=ctx.request_id,
                    version=1,
                    intent=fingerprint.intent.value,
                    domain=fingerprint.domain,
                    data_requirements={"values": [d.value for d in fingerprint.data_requirement]},
                    complexity=fingerprint.complexity.value,
                    sensitivity=fingerprint.sensitivity.value,
                    impact=fingerprint.impact.value,
                    actionability=fingerprint.actionability.value,
                    risk_vector={},  # filled in below once risk is assessed
                    confidence=fingerprint.confidence,
                    capability_hints={"values": [h.value for h in fingerprint.capability_hints]},
                    source=fingerprint.source,
                )
            )
        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="query_profiling",
            status="COMPLETED",
            output_ref={"query_profile_id": profile_id, "intent": fingerprint.intent.value, "complexity": fingerprint.complexity.value},
            completed=True,
        )
        self._publish(
            EventType.QUERY_PROFILED,
            ctx,
            source="controlplane",
            payload={
                "query_profile_id": profile_id,
                "intent": fingerprint.intent.value,
                "capability_hints": [h.value for h in fingerprint.capability_hints],
                "source": fingerprint.source,
            },
        )

        risk = self._risk_profiler.profile(query, fingerprint)
        with session_scope() as session:
            record = session.get(QueryProfileRecord, profile_id)
            record.risk_vector = risk.model_dump(mode="json")

        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="risk_assessment",
            status="COMPLETED",
            output_ref={"severity": risk.severity.value, "recommended_control_depth": risk.recommended_control_depth.value},
            completed=True,
        )
        self._publish(
            EventType.RISK_DETECTED,
            ctx,
            source="controlplane",
            severity=_RISK_TO_EVENT_SEVERITY[risk.severity],
            payload={
                "query_profile_id": profile_id,
                "severity": risk.severity.value,
                "trigger_signals": risk.trigger_signals,
                "recommended_control_depth": risk.recommended_control_depth.value,
            },
        )
        return fingerprint, risk

    def _invoke_model(self, ctx: RequestContext, settings: Settings, query: str) -> dict:
        from controlplane.db.engine import session_scope
        from controlplane.db.models import ModelInvocationRecord

        invocation_id = new_id("inv")
        started_at = _utcnow()

        try:
            provider = self._provider_factory(settings)
            result = provider.generate(prompt=query)
        except ConfigurationError:
            self._record_invocation_failure(
                invocation_id=invocation_id,
                ctx=ctx,
                provider="unknown",
                model="unknown",
                started_at=started_at,
                error_message="model provider is not configured",
            )
            raise
        except ModelProviderTimeout as exc:
            self._record_invocation_failure(
                invocation_id=invocation_id,
                ctx=ctx,
                provider="groq",
                model=settings.groq_model or "unknown",
                started_at=started_at,
                error_message=str(exc),
            )
            raise TimeoutError("model provider timed out") from exc
        except ModelProviderError as exc:
            self._record_invocation_failure(
                invocation_id=invocation_id,
                ctx=ctx,
                provider="groq",
                model=settings.groq_model or "unknown",
                started_at=started_at,
                error_message=str(exc),
            )
            raise DependencyError("model provider call failed") from exc

        completed_at = _utcnow()
        with session_scope() as session:
            session.add(
                ModelInvocationRecord(
                    id=invocation_id,
                    request_id=ctx.request_id,
                    trace_id=ctx.trace_id,
                    trajectory_id=ctx.trajectory_id,
                    provider=result.provider,
                    model=result.model,
                    status="SUCCESS",
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=result.latency_ms,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    input_text=query,
                    output_text=result.content,
                )
            )
        self._ledger.append(
            trajectory_id=ctx.trajectory_id,
            actor_type="SYSTEM",
            actor_id="controlplane-runtime",
            action_type="MODEL_INVOKED",
            consequence_class=ConsequenceClass.READ_ONLY,
            resource_type="model",
            resource_id=result.model,
            evidence_refs={"model_invocation_id": invocation_id},
            metadata={
                "provider": result.provider,
                "status": "SUCCESS",
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )
        self._publish(
            EventType.MODEL_CALLED,
            ctx,
            source="model",
            payload={
                "model_invocation_id": invocation_id,
                "provider": result.provider,
                "model": result.model,
                "latency_ms": result.latency_ms,
            },
        )
        return {
            "invocation_id": invocation_id,
            "provider": result.provider,
            "model": result.model,
            "content": result.content,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }

    def _record_invocation_failure(
        self,
        *,
        invocation_id: str,
        ctx: RequestContext,
        provider: str,
        model: str,
        started_at: datetime,
        error_message: str,
    ) -> None:
        from controlplane.db.engine import session_scope
        from controlplane.db.models import ModelInvocationRecord

        with session_scope() as session:
            session.add(
                ModelInvocationRecord(
                    id=invocation_id,
                    request_id=ctx.request_id,
                    trace_id=ctx.trace_id,
                    trajectory_id=ctx.trajectory_id,
                    provider=provider,
                    model=model,
                    status="FAILURE",
                    started_at=started_at,
                    completed_at=_utcnow(),
                    error_metadata={"message": error_message},
                )
            )
        self._ledger.append(
            trajectory_id=ctx.trajectory_id,
            actor_type="SYSTEM",
            actor_id="controlplane-runtime",
            action_type="MODEL_INVOKED",
            consequence_class=ConsequenceClass.READ_ONLY,
            resource_type="model",
            resource_id=model,
            evidence_refs={"model_invocation_id": invocation_id},
            metadata={"provider": provider, "status": "FAILURE", "error": error_message},
        )
        self._publish(
            EventType.MODEL_FAILURE,
            ctx,
            source="model",
            payload={"model_invocation_id": invocation_id, "provider": provider, "error": error_message},
        )

    def _fail(self, ctx: RequestContext, state: ExecutionState, *, step_id: str | None, error: ControlPlaneError) -> None:
        logger.warning(
            "execution_step_failed", extra={"cp_fields": {"step_id": step_id, "error_code": error.error_code}}
        )
        if step_id is not None:
            self._trajectory_store.update_step_status(
                step_id, "FAILED", output_ref={"error_code": error.error_code}, completed=True
            )
        else:
            self._trajectory_store.append_step(
                trajectory_id=ctx.trajectory_id,
                step_type="query_profiling",
                status="FAILED",
                output_ref={"error_code": error.error_code},
                completed=True,
            )
        self._trajectory_store.update_trajectory_status(
            ctx.trajectory_id, "FAILED", final_status="FAILED", completed=True
        )
        self._trajectory_store.update_request_status(ctx.request_id, "FAILED", completed=True)
        state.fail("model_invocation" if step_id is not None else "query_profiling", error.message)


def build_default_runtime(
    provider_factory=get_configured_provider, query_profiler=None, risk_profiler=None, policy=None
) -> Runtime:
    trajectory_store = TrajectoryStore()
    ledger = ExecutionLedger()
    transport = InProcessEventTransport()
    transport.subscribe(EventStore().persist)
    return Runtime(
        trajectory_store=trajectory_store,
        ledger=ledger,
        event_transport=transport,
        provider_factory=provider_factory,
        query_profiler=query_profiler,
        risk_profiler=risk_profiler,
        policy=policy,
    )
