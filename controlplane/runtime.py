"""Traceable runtime -- Milestone 3.

USER QUERY -> create request/trajectory -> QUERY_RECEIVED -> Query
Profiler -> QUERY_PROFILED -> Risk Profiler + Policy -> RISK_DETECTED ->
Capability Router + Model Router -> PLAN_CREATED (+ HUMAN_REVIEW_REQUIRED
when applicable) -> Execution Graph run by the Graph Executor
(ROUTE_STARTED/ROUTE_COMPLETED per node; the "generation" node invokes
the configured model provider for the routed role) -> model invocation
record -> ledger entry -> FINAL_RESPONSE_GENERATED -> update trajectory
-> structured response.

Still no RAG, evaluation, intervention, or replanning. SQL/RAG/WEB/
CHAT_HISTORY/MEMORY/AGENT capability nodes run via the executor's
explicit MOCKED handler -- see controlplane/execution/executor.py -- so
a query can be *routed* to them, but no real data is fetched and no real
action is performed yet (Layer 5/11/18, see
docs/PROJECT_STATE/FUTURE_WORK.md). See docs/PROJECT_STATE/FUTURE_WORK.md
for the full list of what's still ahead.
"""

from __future__ import annotations

from datetime import datetime, timezone

from controlplane.config import Settings, get_settings
from controlplane.context import RequestContext
from controlplane.db.models import RouteDecisionRecord, new_id
from controlplane.errors import ConfigurationError, ControlPlaneError, DependencyError, TimeoutError
from controlplane.events.schema import Event, EventType, Severity
from controlplane.events.store import EventStore
from controlplane.events.transport import EventTransport, InProcessEventTransport
from controlplane.execution.executor import GraphExecutor
from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus
from controlplane.ledger.ledger import ConsequenceClass, ExecutionLedger
from controlplane.logging_config import get_logger
from controlplane.models.provider import ModelProviderError, ModelProviderTimeout
from controlplane.models.registry import get_configured_provider, resolve_model_name
from controlplane.policy.baseline import PolicyBaseline, PolicyDecision
from controlplane.query_intelligence.fingerprint import QueryFingerprint
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import RiskProfile, RiskSeverity
from controlplane.routing.capability_router import CapabilityRoute, CapabilityRouter
from controlplane.routing.model_router import ModelRouteAction, ModelRouteDecision, ModelRouter
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
        capability_router=None,
        model_router=None,
        graph_executor=None,
    ) -> None:
        self._trajectory_store = trajectory_store
        self._ledger = ledger
        self._events = event_transport
        self._settings_provider = settings_provider
        self._provider_factory = provider_factory
        self._query_profiler = query_profiler or HybridQueryProfiler()
        self._risk_profiler = risk_profiler or BaselineRiskProfiler()
        self._policy = policy or PolicyBaseline()
        self._capability_router = capability_router or CapabilityRouter()
        self._model_router = model_router or ModelRouter()
        self._graph_executor = graph_executor or GraphExecutor(handlers={})

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
            fingerprint, risk, profile_id = self._profile_and_assess_risk(ctx, query)
        except ControlPlaneError as exc:
            self._fail(ctx, state, step_id=None, error=exc)
            raise
        policy_decision = self._policy.decide(risk.severity)
        state.metadata["query_profile"] = fingerprint.model_dump(mode="json")
        state.metadata["risk"] = risk.model_dump(mode="json")
        state.metadata["policy"] = policy_decision.model_dump(mode="json")

        capability_route, model_decision = self._route(ctx, profile_id, fingerprint, risk, policy_decision)
        state.metadata["model_route"] = model_decision.model_dump(mode="json")
        # capability_route.to_dict() (which includes per-node graph status)
        # is snapshotted after execution below, not here, so the caller sees
        # final node statuses rather than the pre-execution PENDING placeholder.

        state.advance("routing", ExecutionStatus.PROCESSING)
        self._trajectory_store.update_trajectory_status(ctx.trajectory_id, "PROCESSING")

        if model_decision.action == ModelRouteAction.ABSTAIN:
            self._abstain(ctx, state, capability_route, model_decision)
            # Snapshotted after execution (here, after every node was marked
            # SKIPPED) so the graph the caller sees reflects final status,
            # not the PENDING placeholder it had before anything ran.
            state.metadata["capability_route"] = capability_route.to_dict()
            state.advance("completed", ExecutionStatus.COMPLETED)
            return state

        try:
            result = self._execute_graph(ctx, settings, query, capability_route, model_decision)
        except ControlPlaneError as exc:
            state.metadata["capability_route"] = capability_route.to_dict()
            self._fail(ctx, state, step_id=None, error=exc, step_type="generation", record_step=False)
            raise
        state.metadata["capability_route"] = capability_route.to_dict()

        state.metadata["answer"] = result["content"]
        state.metadata["model"] = {
            "provider": result["provider"],
            "model": result["model"],
            "role": model_decision.model_role,
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

    def _profile_and_assess_risk(self, ctx: RequestContext, query: str) -> tuple[QueryFingerprint, RiskProfile, str]:
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
        return fingerprint, risk, profile_id

    def _route(
        self,
        ctx: RequestContext,
        profile_id: str,
        fingerprint: QueryFingerprint,
        risk: RiskProfile,
        policy_decision: PolicyDecision,
    ) -> tuple[CapabilityRoute, ModelRouteDecision]:
        from controlplane.db.engine import session_scope

        capability_route = self._capability_router.route(fingerprint, risk, policy_decision)
        model_decision = self._model_router.decide(fingerprint, risk, policy_decision)

        with session_scope() as session:
            session.add(
                RouteDecisionRecord(
                    id=new_id("route"),
                    request_id=ctx.request_id,
                    trajectory_id=ctx.trajectory_id,
                    query_profile_id=profile_id,
                    capability_router_version=self._capability_router.name,
                    selected_capabilities={"values": capability_route.selected_capabilities},
                    restricted_capabilities={"values": capability_route.restricted_removed},
                    capability_reason=capability_route.reason,
                    execution_graph=capability_route.graph.to_dict(),
                    model_router_version=self._model_router.name,
                    model_action=model_decision.action.value,
                    model_role=model_decision.model_role,
                    require_verification=model_decision.require_verification,
                    human_approval_required=model_decision.human_approval_required,
                    model_reason=model_decision.reason,
                    expected_cost_class=model_decision.expected_cost_class,
                    expected_latency_class=model_decision.expected_latency_class,
                )
            )

        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="routing",
            status="COMPLETED",
            output_ref={
                "selected_capabilities": capability_route.selected_capabilities,
                "restricted_removed": capability_route.restricted_removed,
                "model_action": model_decision.action.value,
                "model_role": model_decision.model_role,
            },
            completed=True,
        )
        self._publish(
            EventType.PLAN_CREATED,
            ctx,
            source="controlplane",
            payload={
                "selected_capabilities": capability_route.selected_capabilities,
                "restricted_removed": capability_route.restricted_removed,
                "graph": capability_route.graph.to_dict(),
                "model_action": model_decision.action.value,
                "model_role": model_decision.model_role,
            },
        )
        if model_decision.action in (ModelRouteAction.HUMAN_REVIEW, ModelRouteAction.ABSTAIN):
            self._publish(
                EventType.HUMAN_REVIEW_REQUIRED,
                ctx,
                source="controlplane",
                severity=Severity.HIGH,
                payload={"reason": model_decision.reason, "model_action": model_decision.action.value},
            )
        return capability_route, model_decision

    def _abstain(
        self,
        ctx: RequestContext,
        state: ExecutionState,
        capability_route: CapabilityRoute,
        model_decision: ModelRouteDecision,
    ) -> None:
        for node in capability_route.graph.nodes:
            node.status = NodeStatus.SKIPPED
        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="generation",
            status="SKIPPED",
            output_ref={"reason": model_decision.reason},
            completed=True,
        )
        self._publish(
            EventType.FINAL_RESPONSE_GENERATED,
            ctx,
            source="controlplane",
            payload={"abstained": True, "reason": model_decision.reason},
        )
        self._trajectory_store.update_trajectory_status(
            ctx.trajectory_id, "COMPLETED", final_status="ABSTAINED", completed=True
        )
        self._trajectory_store.update_request_status(ctx.request_id, "COMPLETED", completed=True)
        state.metadata["answer"] = None

    def _execute_graph(
        self,
        ctx: RequestContext,
        settings: Settings,
        query: str,
        capability_route: CapabilityRoute,
        model_decision: ModelRouteDecision,
    ) -> dict:
        captured: dict = {}
        handlers = {"generation": self._generation_handler(ctx, settings, query, model_decision.model_role, captured)}
        executor = GraphExecutor(handlers=handlers)
        graph_result = executor.run(capability_route.graph, mode="parallel")

        for node in capability_route.graph.nodes:
            self._publish(
                EventType.ROUTE_STARTED,
                ctx,
                source="execution_graph",
                payload={"node_id": node.node_id, "capability": node.capability},
            )
            self._trajectory_store.append_step(
                trajectory_id=ctx.trajectory_id,
                step_type=f"route:{node.node_id}",
                status=node.status.value,
                input_ref={"capability": node.capability, "depends_on": list(node.depends_on)},
                output_ref=node.output_ref if node.status != NodeStatus.FAILED else {"error": node.error},
                completed=True,
            )
            self._publish(
                EventType.ROUTE_COMPLETED,
                ctx,
                source="execution_graph",
                payload={"node_id": node.node_id, "status": node.status.value, "latency_ms": node.latency_ms},
            )

        if "generation" in graph_result.failed:
            raise captured["error"]
        return captured["result"]

    def _generation_handler(self, ctx: RequestContext, settings: Settings, query: str, role: str, captured: dict):
        def handler(node) -> dict:
            try:
                result = self._invoke_model(ctx, settings, query, role=role)
            except ControlPlaneError as exc:
                # GraphExecutor only records str(exc) on the node; stash the
                # real exception so _execute_graph can re-raise the correct
                # typed error (DependencyError/TimeoutError/ConfigurationError)
                # after all nodes have been persisted, instead of losing its
                # type to the executor's generic failure handling.
                captured["error"] = exc
                raise
            captured["result"] = result
            return {
                "model_invocation_id": result["invocation_id"],
                "provider": result["provider"],
                "model": result["model"],
            }

        return handler

    def _invoke_model(self, ctx: RequestContext, settings: Settings, query: str, role: str = "STRONG") -> dict:
        from controlplane.db.engine import session_scope
        from controlplane.db.models import ModelInvocationRecord

        invocation_id = new_id("inv")
        started_at = _utcnow()
        resolved_model = resolve_model_name(settings, role) or "unknown"

        try:
            provider = self._provider_factory(settings, role=role)
            result = provider.generate(prompt=query)
        except ConfigurationError:
            self._record_invocation_failure(
                invocation_id=invocation_id,
                ctx=ctx,
                provider="unknown",
                model=resolved_model,
                started_at=started_at,
                error_message="model provider is not configured",
            )
            raise
        except ModelProviderTimeout as exc:
            self._record_invocation_failure(
                invocation_id=invocation_id,
                ctx=ctx,
                provider="groq",
                model=resolved_model,
                started_at=started_at,
                error_message=str(exc),
            )
            raise TimeoutError("model provider timed out") from exc
        except ModelProviderError as exc:
            self._record_invocation_failure(
                invocation_id=invocation_id,
                ctx=ctx,
                provider="groq",
                model=resolved_model,
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
                "role": role,
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
                "role": role,
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

    def _fail(
        self,
        ctx: RequestContext,
        state: ExecutionState,
        *,
        step_id: str | None,
        error: ControlPlaneError,
        step_type: str = "query_profiling",
        record_step: bool = True,
    ) -> None:
        """``record_step=False`` for a graph-execution failure: ``_execute_graph``
        already persisted an accurate per-node ``route:<node_id>`` FAILED
        step before raising, so this call only needs to finalize the
        trajectory/request -- appending another step here would duplicate
        it under a less specific label."""
        logger.warning(
            "execution_step_failed", extra={"cp_fields": {"step_id": step_id, "error_code": error.error_code}}
        )
        if record_step:
            if step_id is not None:
                self._trajectory_store.update_step_status(
                    step_id, "FAILED", output_ref={"error_code": error.error_code}, completed=True
                )
            else:
                self._trajectory_store.append_step(
                    trajectory_id=ctx.trajectory_id,
                    step_type=step_type,
                    status="FAILED",
                    output_ref={"error_code": error.error_code},
                    completed=True,
                )
        self._trajectory_store.update_trajectory_status(
            ctx.trajectory_id, "FAILED", final_status="FAILED", completed=True
        )
        self._trajectory_store.update_request_status(ctx.request_id, "FAILED", completed=True)
        state.fail(step_type, error.message)


def build_default_runtime(
    provider_factory=get_configured_provider,
    query_profiler=None,
    risk_profiler=None,
    policy=None,
    capability_router=None,
    model_router=None,
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
        capability_router=capability_router,
        model_router=model_router,
    )
