"""Traceable runtime -- current through Milestone 9 (real local
generative provider, corpus-affinity RAG routing, Shadow Mode).

USER QUERY -> create request/trajectory -> QUERY_RECEIVED -> Query
Profiler -> QUERY_PROFILED -> Risk Profiler + Policy -> RISK_DETECTED ->
Capability Router + Model Router -> PLAN_CREATED (+ HUMAN_REVIEW_REQUIRED
when applicable) -> Execution Graph run by the Graph Executor
(ROUTE_STARTED/ROUTE_COMPLETED per node; "SQL", "RAG", and "AGENT" nodes
run real capabilities -- controlplane/capabilities/ -- and "generation"
invokes the configured model provider for the routed role, with the
prompt rebuilt from any completed SQL/RAG evidence) -> Evaluation
(controlplane/evaluation/) -> Decide -> (Intervene -> Replan ->
re-Evaluate)* -> Verify -> Trust -> FINAL_RESPONSE_GENERATED -> update
trajectory -> structured response.

WEB/CHAT_HISTORY/MEMORY capability nodes still run via the executor's
explicit MOCKED handler (AGENT became real in Milestone 7; Web/Chat/
Memory are still future work, see docs/PROJECT_STATE/FUTURE_WORK.md).

The generation node uses whatever ``provider_factory`` resolves for the
routed role. Since Milestone 9 that falls back to a real LOCAL model
(controlplane/models/local_generation_provider.py) when no API key is
configured, so this whole path runs end-to-end offline -- previously it
could not run at all without a key, which is why every end-to-end
scenario in the project used scripted fakes.

SHADOW MODE (``shadow_mode=True``): everything above runs unchanged --
routing, retrieval, evaluation, and the Decision Engine all execute and
are recorded -- but no consequence is applied: no intervention runs, no
answer is withheld, and the pre-execution ABSTAIN refusal does not fire.
See controlplane/governance/shadow_mode.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from controlplane.capabilities.agent_capability import AgentCapability
from controlplane.capabilities.rag_capability import RAGCapability
from controlplane.capabilities.sql_capability import SQLCapability
from controlplane.config import Settings, get_settings
from controlplane.context import RequestContext
from controlplane.db.models import (
    DecisionRecord,
    InterventionRecord,
    ReplanRecord,
    ResponseEvaluationRecord,
    RouteDecisionRecord,
    VerificationRecord,
    new_id,
)
from controlplane.decision.engine import ControlAction, ControlDecision, DecisionEngine
from controlplane.errors import ConfigurationError, ControlPlaneError, DependencyError, TimeoutError
from controlplane.evaluation.evaluators import EvaluationContext, EvaluationResult, EvaluationSuite
from controlplane.events.schema import Event, EventType, Severity
from controlplane.intervention.engine import InterventionEngine, InterventionSpec, InterventionType
from controlplane.events.store import EventStore
from controlplane.events.transport import EventTransport, InProcessEventTransport
from controlplane.execution.executor import GraphExecutor
from controlplane.governance.shadow_mode import verdict_for as shadow_mode_verdict_for
from controlplane.execution.graph import ExecutionGraph, ExecutionNode, NodeStatus
from controlplane.ledger.ledger import ConsequenceClass, ExecutionLedger
from controlplane.logging_config import get_logger
from controlplane.models.provider import ModelProviderError, ModelProviderTimeout
from controlplane.models.registry import get_configured_provider, resolve_model_name
from controlplane.planning.replanner import Replanner
from controlplane.policy.baseline import PolicyBaseline, PolicyDecision
from controlplane.query_intelligence.fingerprint import QueryFingerprint
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler
from controlplane.risk.baseline import BaselineRiskProfiler
from controlplane.risk.profile import RiskProfile, RiskSeverity
from controlplane.routing.capability_router import CapabilityRoute, CapabilityRouter
from controlplane.routing.model_router import ModelRouteAction, ModelRouteDecision, ModelRouter
from controlplane.state import ExecutionState, ExecutionStatus
from controlplane.trajectory.store import TrajectoryStore
from controlplane.trust.engine import TrustEngine
from controlplane.verification.engine import VerificationEngine, VerificationResult, VerificationStatus

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
        sql_capability=None,
        rag_capability=None,
        agent_capability=None,
        evaluation_suite=None,
        decision_engine=None,
        intervention_engine=None,
        verification_engine=None,
        trust_engine=None,
        replanner=None,
        shadow_mode: bool = False,
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
        self._sql_capability = sql_capability or SQLCapability()
        self._rag_capability = rag_capability or RAGCapability()
        self._agent_capability = agent_capability or AgentCapability()
        self._evaluation_suite = evaluation_suite or EvaluationSuite()
        self._decision_engine = decision_engine or DecisionEngine()
        self._intervention_engine = intervention_engine or InterventionEngine()
        self._verification_engine = verification_engine or VerificationEngine()
        self._trust_engine = trust_engine or TrustEngine()
        # Dynamic replanning (Milestone 10): proposes real graph changes.
        self._replanner = replanner or Replanner()
        # Shadow Mode (Milestone 9): observe and record, never enforce.
        # See controlplane/governance/shadow_mode.py for what is and is
        # not suppressed.
        self._shadow_mode = shadow_mode

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

        capability_route, model_decision, route_record_id = self._route(ctx, profile_id, fingerprint, risk, policy_decision)
        state.metadata["model_route"] = model_decision.model_dump(mode="json")
        # capability_route.to_dict() (which includes per-node graph status)
        # is snapshotted after execution below, not here, so the caller sees
        # final node statuses rather than the pre-execution PENDING placeholder.

        state.advance("routing", ExecutionStatus.PROCESSING)
        self._trajectory_store.update_trajectory_status(ctx.trajectory_id, "PROCESSING")

        # Shadow Mode never refuses before execution: the point is to
        # observe what the unmanaged system would have produced AND what
        # ControlPlane would have done about it. Refusing here would
        # destroy half of that observation.
        if model_decision.action == ModelRouteAction.ABSTAIN and not self._shadow_mode:
            self._abstain(ctx, state, capability_route, model_decision)
            # Snapshotted after execution (here, after every node was marked
            # SKIPPED) so the graph the caller sees reflects final status,
            # not the PENDING placeholder it had before anything ran.
            state.metadata["capability_route"] = capability_route.to_dict()
            self._persist_final_graph_snapshot(route_record_id, capability_route)
            state.advance("completed", ExecutionStatus.COMPLETED)
            return state

        try:
            result = self._execute_graph(ctx, settings, query, capability_route, model_decision)
        except ControlPlaneError as exc:
            state.metadata["capability_route"] = capability_route.to_dict()
            self._fail(ctx, state, step_id=None, error=exc, step_type="generation", record_step=False)
            raise
        evaluation_results = self._run_evaluation(ctx, capability_route, fingerprint, risk, query, result["content"])

        final_answer, final_result, final_role, final_evaluation, decision, verification = self._run_control_loop(
            ctx, settings, query, capability_route, model_decision, risk, fingerprint, result, evaluation_results,
        )
        state.metadata["capability_route"] = capability_route.to_dict()
        self._persist_final_graph_snapshot(route_record_id, capability_route)
        state.metadata["answer"] = final_answer
        state.metadata["model"] = {
            "provider": final_result["provider"],
            "model": final_result["model"],
            "role": final_role,
            "latency_ms": final_result["latency_ms"],
            "input_tokens": final_result["input_tokens"],
            "output_tokens": final_result["output_tokens"],
        }
        state.metadata["evaluation"] = [r.model_dump(mode="json") for r in final_evaluation]
        state.metadata["decision"] = decision.model_dump(mode="json")
        state.metadata["verification"] = verification.model_dump(mode="json")
        trust = self._trust_engine.assess(verification, decision, risk)
        state.metadata["trust"] = trust.model_dump(mode="json")

        self._publish(
            EventType.FINAL_RESPONSE_GENERATED,
            ctx,
            source="controlplane",
            payload={
                "model_invocation_id": final_result["invocation_id"],
                "verification_status": verification.status.value,
                "trust_level": trust.level.value,
            },
        )
        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="completed",
            status="COMPLETED",
            output_ref={"model_invocation_id": final_result["invocation_id"], "verification_status": verification.status.value},
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
    ) -> tuple[CapabilityRoute, ModelRouteDecision, str]:
        from controlplane.db.engine import session_scope

        capability_route = self._capability_router.route(fingerprint, risk, policy_decision)
        model_decision = self._model_router.decide(fingerprint, risk, policy_decision)

        route_record_id = new_id("route")
        with session_scope() as session:
            session.add(
                RouteDecisionRecord(
                    id=route_record_id,
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
        return capability_route, model_decision, route_record_id

    def _attempt_capability_replan(
        self,
        ctx: RequestContext,
        query: str,
        capability_route: CapabilityRoute,
        fingerprint: QueryFingerprint,
        evaluation_results: list[EvaluationResult],
    ):
        """Try to change the PLAN, not just re-run the same node harder.

        Milestone 10 (§8/§38/§46): asks the Capability Registry whether a
        capability exists that serves a data requirement of THIS query
        which nothing in the current plan serves. If so, the node is added
        to the graph, executed, and its evidence rewired into the merge
        node so it actually reaches the generation prompt.

        INSUFFICIENT evidence and CONFLICTING evidence are different
        problems and get different responses. Adding a new data source
        cannot resolve a contradiction between two sources that already
        disagree -- it just supplies a third opinion, and the architecture's
        answer to conflicting evidence is to widen retrieval in search of
        an authoritative source and then disclose the conflict rather than
        pick a side (see the Milestone 6 conflicting-evidence scenario).
        Conflating the two was a real regression caught by that scenario's
        existing test.

        Returns the ``PlanChange`` (which may be ``changed=False``), or
        ``None`` if the new node could not be executed -- in which case the
        caller falls back to widening retrieval rather than proceeding with
        a node that produced nothing.
        """
        if any(r.label == "CONFLICTING" for r in evaluation_results):
            logger.info(
                "capability_replan_skipped_for_conflicting_evidence",
                extra={"cp_fields": {"reason": "conflicting evidence needs an authoritative source, "
                                                "not an additional one"}},
            )
            return None
        proposal, descriptor = self._replanner.propose_additional_evidence_capability(
            graph=capability_route.graph,
            data_requirements={d.value for d in fingerprint.data_requirement},
            restricted_capabilities=set(capability_route.restricted_removed),
        )
        if not proposal.changed or descriptor is None:
            logger.info(
                "capability_replan_declined",
                extra={"cp_fields": {"reason": proposal.rejected_reason}},
            )
            return proposal

        applied = self._replanner.apply(capability_route.graph, descriptor)
        if not applied.changed:
            return applied

        node_id = applied.added_nodes[0]
        node = capability_route.graph.get(node_id)
        handler = {"SQL": self._sql_capability, "RAG": self._rag_capability}.get(descriptor.capability_id)
        if handler is None:
            # The registry offered a capability this runtime has no live
            # handler for. Mark it SKIPPED and fall back -- never leave a
            # PENDING node in the graph pretending it contributed.
            node.status = NodeStatus.SKIPPED
            node.error = f"no live handler wired for capability {descriptor.capability_id}"
            return None

        try:
            node.output_ref = handler.execute(query)
            node.status = NodeStatus.COMPLETED
        except Exception as exc:  # a new capability failing must not fail the request
            node.status = NodeStatus.FAILED
            node.error = str(exc)
            logger.warning(
                "replan_capability_execution_failed",
                extra={"cp_fields": {"capability": descriptor.capability_id, "error": str(exc)}},
            )
            return None

        self._publish(
            EventType.REPLAN_TRIGGERED, ctx, source="controlplane",
            payload={
                "plan_change": "ADD_NODE",
                "added_capability": descriptor.capability_id,
                "added_node": node_id,
                "reason": proposal.reason,
            },
        )
        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type=f"replan:add_{descriptor.capability_id.lower()}",
            status="COMPLETED",
            input_ref={"reason": proposal.reason},
            output_ref={"added_node": node_id, "capability": descriptor.capability_id},
            completed=True,
        )
        return applied

    def _persist_final_graph_snapshot(self, route_record_id: str, capability_route: CapabilityRoute) -> None:
        """Rewrite the persisted execution graph with FINAL node statuses.

        Milestone 10 fix, found while validating component-level failure
        localization against real persisted data: ``route_decisions.execution_graph``
        was written at routing time, before the graph ran, so every node
        status in the database was frozen at PENDING forever. The
        in-memory ``state.metadata`` copy was updated post-execution, but
        the DB row -- which is what the dashboard and any offline
        diagnostics read -- never was.

        That made the dashboard misreport which capabilities actually
        executed, and it directly undermined failure localization, which
        uses node status to distinguish "retrieval ran and the model
        ignored the evidence" (a generation failure) from "retrieval
        never ran at all" (a routing failure).
        """
        from sqlalchemy.exc import SQLAlchemyError

        from controlplane.db.engine import session_scope

        try:
            with session_scope() as session:
                record = session.get(RouteDecisionRecord, route_record_id)
                if record is not None:
                    record.execution_graph = capability_route.graph.to_dict()
        except SQLAlchemyError:
            # Observability must never break the request it observes.
            logger.warning(
                "graph_snapshot_persist_failed",
                extra={"cp_fields": {"route_record_id": route_record_id}},
            )

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
        handlers = {
            "generation": self._generation_handler(
                ctx, settings, query, model_decision.model_role, captured, capability_route.graph
            ),
            "SQL": lambda node: self._sql_capability.execute(query),
            "RAG": lambda node: self._rag_capability.execute(query),
            "AGENT": lambda node: self._agent_capability.execute(query),
        }
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
            if node.capability == "AGENT" and node.status == NodeStatus.COMPLETED:
                self._record_agent_action(ctx, node.output_ref)

        if "generation" in graph_result.failed:
            raise captured["error"]
        return captured["result"]

    def _record_agent_action(self, ctx: RequestContext, agent_result: dict) -> None:
        """Real audit trail for a governed tool proposal (bootstrap:
        "TOOL RESULT -> TRAJECTORY -> LEDGER -> POST-ACTION CHECK ->
        VERIFY") -- every proposal lands here, whatever the outcome,
        never only the ones that actually ran."""
        governance_action = agent_result.get("governance_action", "ALLOW")
        consequence = agent_result.get("consequence_class", "READ_ONLY")

        severity = {
            "BLOCK": Severity.CRITICAL, "HUMAN_REVIEW": Severity.HIGH,
            "RESTRICT": Severity.WARNING, "ALLOW": Severity.NOTICE,
        }.get(governance_action, Severity.NOTICE)
        self._publish(
            EventType.AGENT_ACTION_GOVERNED,
            ctx,
            source="agent_capability",
            severity=severity,
            payload={
                "proposed_tool": agent_result.get("proposed_tool"),
                "governance_action": governance_action,
                "execution_status": agent_result.get("execution_status"),
                "consequence_class": consequence,
            },
        )
        if governance_action == "HUMAN_REVIEW":
            self._publish(
                EventType.HUMAN_REVIEW_REQUIRED,
                ctx,
                source="agent_capability",
                severity=Severity.HIGH,
                payload={"reason": agent_result.get("governance_reason"), "proposed_tool": agent_result.get("proposed_tool")},
            )

        try:
            consequence_class = ConsequenceClass(consequence)
        except ValueError:
            consequence_class = ConsequenceClass.READ_ONLY
        self._ledger.append(
            trajectory_id=ctx.trajectory_id,
            actor_type="AGENT",
            actor_id=agent_result.get("proposed_tool", "unknown_tool"),
            action_type="AGENT_TOOL_PROPOSED",
            consequence_class=consequence_class,
            resource_type="tool",
            resource_id=agent_result.get("proposed_tool", "unknown_tool"),
            evidence_refs={"tool_call": agent_result.get("tool_call")},
            metadata={
                "governance_action": governance_action,
                "governance_reason": agent_result.get("governance_reason"),
                "execution_status": agent_result.get("execution_status"),
            },
        )

    def _run_evaluation(
        self,
        ctx: RequestContext,
        capability_route: CapabilityRoute,
        fingerprint: QueryFingerprint,
        risk: RiskProfile,
        query: str,
        answer: str,
    ) -> list[EvaluationResult]:
        from controlplane.db.engine import session_scope

        evidence_texts: list[str] = []
        sql_rows: list[dict] = []
        rag_adequacy: str | None = None
        agent_governance_action: str | None = None
        for node in capability_route.graph.nodes:
            if node.capability == "RAG" and node.status == NodeStatus.COMPLETED:
                evidence_texts.extend(item["text"] for item in node.output_ref.get("evidence", []))
                rag_adequacy = node.output_ref.get("adequacy", {}).get("label")
            if node.capability == "SQL" and node.status == NodeStatus.COMPLETED:
                sql_rows.extend(node.output_ref.get("rows", []))
            if node.capability == "AGENT" and node.status == NodeStatus.COMPLETED:
                agent_governance_action = node.output_ref.get("governance_action")

        eval_ctx = EvaluationContext(
            query=query, answer=answer, evidence_texts=evidence_texts, sql_rows=sql_rows,
            rag_adequacy=rag_adequacy, agent_governance_action=agent_governance_action,
            fingerprint=fingerprint, risk=risk,
        )
        results = self._evaluation_suite.run(eval_ctx)

        with session_scope() as session:
            for r in results:
                session.add(
                    ResponseEvaluationRecord(
                        id=new_id("respeval"),
                        request_id=ctx.request_id,
                        trajectory_id=ctx.trajectory_id,
                        evaluator=r.evaluator,
                        status=r.status.value,
                        label=r.label,
                        score=r.score,
                        result=r.model_dump(mode="json"),
                    )
                )

        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type="evaluation",
            status="COMPLETED",
            output_ref={
                "evaluators": [r.evaluator for r in results],
                "implemented": [r.evaluator for r in results if r.status.value == "IMPLEMENTED"],
            },
            completed=True,
        )
        self._publish(
            EventType.EVALUATION_COMPLETED,
            ctx,
            source="controlplane",
            payload={"results": [{"evaluator": r.evaluator, "status": r.status.value, "label": r.label} for r in results]},
        )
        return results

    def _run_control_loop(
        self,
        ctx: RequestContext,
        settings: Settings,
        query: str,
        capability_route: CapabilityRoute,
        model_decision: ModelRouteDecision,
        risk: RiskProfile,
        fingerprint: QueryFingerprint,
        result: dict,
        evaluation_results: list[EvaluationResult],
    ) -> tuple[str | None, dict, str, list[EvaluationResult], ControlDecision, VerificationResult]:
        """Decide -> (Intervene -> Replan -> re-Evaluate)* -> Verify.
        Bounded to at most ``DecisionEngine._max_attempts - 1`` retries by
        the Decision Engine itself (a decision with ``can_retry=False``
        never requests another intervention) -- the ``for`` loop below is
        an additional, independent hard cap (bootstrap SS19: "do not
        retry forever"), not the only thing preventing an infinite loop.
        """
        from controlplane.db.engine import session_scope

        current_role = model_decision.model_role
        attempt = 1
        decision = self._decision_engine.decide(evaluation_results, risk, model_decision, attempt_number=attempt)
        decision_id = self._record_decision(ctx, decision)

        # Shadow Mode: the decision was still computed and recorded above
        # (that IS the observation), but no consequence is applied -- no
        # intervention runs, and the answer below is never withheld.
        shadow_verdict = shadow_mode_verdict_for(decision) if self._shadow_mode else None

        _HARD_MAX_ITERATIONS = 5  # independent of DecisionEngine's own bound -- see docstring
        for _ in range(_HARD_MAX_ITERATIONS if not self._shadow_mode else 0):
            if not decision.requires_intervention:
                break

            if decision.action == ControlAction.RETRIEVE_MORE:
                self._publish(
                    EventType.RETRIEVAL_INSUFFICIENT, ctx, source="controlplane",
                    payload={"reason": decision.reason, "attempt_number": decision.attempt_number},
                )

            spec = self._intervention_engine.plan(decision, current_model_role=current_role)
            self._publish(
                EventType.INTERVENTION_TRIGGERED, ctx, source="controlplane",
                payload={"intervention_type": spec.intervention_type.value, "reason": spec.reason},
            )
            intervention_id = self._record_intervention(ctx, decision_id, spec)

            new_role = spec.new_model_role or current_role
            plan_changed = spec.intervention_type in (InterventionType.RETRIEVE_MORE, InterventionType.CHANGE_MODEL)
            if plan_changed:
                self._publish(
                    EventType.REPLAN_TRIGGERED, ctx, source="controlplane",
                    payload={"intervention_type": spec.intervention_type.value, "reason": spec.reason},
                )
                self._record_replan(ctx, capability_route, spec)
            if spec.intervention_type == InterventionType.CHANGE_MODEL:
                self._publish(
                    EventType.MODEL_ESCALATION, ctx, source="controlplane",
                    payload={"from_role": current_role, "to_role": new_role, "reason": spec.reason},
                )

            plan_change = None
            try:
                if spec.intervention_type == InterventionType.RETRIEVE_MORE:
                    # Milestone 10: try a REAL plan change first -- add a
                    # capability that serves a data requirement nothing in
                    # the current plan serves. Only if no such capability
                    # exists do we fall back to re-running the same
                    # retrieval with a wider k (the Milestone 5 behaviour,
                    # which changed plan_version without changing the graph).
                    plan_change = self._attempt_capability_replan(
                        ctx, query, capability_route, fingerprint, evaluation_results
                    )
                    if plan_change is None or not plan_change.changed:
                        rag_node = next((n for n in capability_route.graph.nodes if n.capability == "RAG"), None)
                        if rag_node is not None:
                            rag_node.output_ref = self._rag_capability.execute(query, k=spec.new_rag_k)
                prompt = self._build_generation_prompt(query, capability_route.graph)
                new_result = self._invoke_model(ctx, settings, prompt, role=new_role)
                actual_effect = {"status": "EXECUTED", "new_content_preview": new_result["content"][:200]}
                if plan_change is not None and plan_change.changed:
                    actual_effect["plan_change"] = plan_change.to_dict()
            except ControlPlaneError as exc:
                logger.warning(
                    "intervention_execution_failed",
                    extra={"cp_fields": {"intervention_type": spec.intervention_type.value, "error": str(exc)}},
                )
                actual_effect = {"status": "FAILED", "error": str(exc)}
                self._record_intervention_outcome(intervention_id, actual_effect)
                break  # keep the previous (pre-intervention) result/evaluation rather than crashing the request
            self._record_intervention_outcome(intervention_id, actual_effect)

            if plan_changed:
                self._publish(
                    EventType.REPLAN_COMPLETED, ctx, source="controlplane",
                    payload={"intervention_type": spec.intervention_type.value},
                )

            result = new_result
            current_role = new_role
            evaluation_results = self._run_evaluation(ctx, capability_route, fingerprint, risk, query, result["content"])
            attempt += 1
            decision = self._decision_engine.decide(evaluation_results, risk, model_decision, attempt_number=attempt)
            decision_id = self._record_decision(ctx, decision)

        verification = self._verification_engine.verify(evaluation_results, decision)
        with session_scope() as session:
            session.add(
                VerificationRecord(
                    id=new_id("verif"),
                    request_id=ctx.request_id,
                    trajectory_id=ctx.trajectory_id,
                    status=verification.status.value,
                    reason=verification.reason,
                    checked_evaluators=verification.checked_evaluators,
                )
            )
        if verification.status in (VerificationStatus.NOT_VERIFIED, VerificationStatus.REJECTED):
            self._publish(
                EventType.VERIFICATION_FAILED, ctx, source="controlplane",
                payload={"status": verification.status.value, "reason": verification.reason},
            )

        final_answer = result["content"]
        if decision.action == ControlAction.ASK_CLARIFICATION and not self._shadow_mode:
            final_answer = None

        if shadow_verdict is not None:
            self._publish(
                EventType.SHADOW_DECISION_RECORDED, ctx, source="controlplane",
                payload={"verdict": shadow_verdict.value, "would_be_action": decision.action.value,
                          "reason": decision.reason},
            )

        return final_answer, result, current_role, evaluation_results, decision, verification

    def _record_decision(self, ctx: RequestContext, decision: ControlDecision) -> str:
        from controlplane.db.engine import session_scope

        decision_id = new_id("dec")
        with session_scope() as session:
            session.add(
                DecisionRecord(
                    id=decision_id,
                    request_id=ctx.request_id,
                    trajectory_id=ctx.trajectory_id,
                    action=decision.action.value,
                    reason=decision.reason,
                    triggering_evaluator=decision.triggering_evaluator,
                    attempt_number=decision.attempt_number,
                    can_retry=decision.can_retry,
                )
            )
        self._trajectory_store.append_step(
            trajectory_id=ctx.trajectory_id,
            step_type=f"decision:{decision.attempt_number}",
            status="COMPLETED",
            output_ref={"action": decision.action.value, "reason": decision.reason},
            completed=True,
        )
        return decision_id

    def _record_intervention(self, ctx: RequestContext, decision_id: str, spec: InterventionSpec) -> str:
        from controlplane.db.engine import session_scope

        intervention_id = new_id("interv")
        with session_scope() as session:
            session.add(
                InterventionRecord(
                    id=intervention_id,
                    request_id=ctx.request_id,
                    trajectory_id=ctx.trajectory_id,
                    decision_id=decision_id,
                    intervention_type=spec.intervention_type.value,
                    reason=spec.reason,
                    spec=spec.model_dump(mode="json"),
                    expected_effect=spec.expected_effect,
                )
            )
        return intervention_id

    def _record_intervention_outcome(self, intervention_id: str, actual_effect: dict) -> None:
        from controlplane.db.engine import session_scope

        with session_scope() as session:
            record = session.get(InterventionRecord, intervention_id)
            if record is not None:
                record.actual_effect = actual_effect

    def _record_replan(self, ctx: RequestContext, capability_route: CapabilityRoute, spec: InterventionSpec) -> None:
        from sqlalchemy import desc, select

        from controlplane.db.engine import session_scope

        with session_scope() as session:
            latest = session.execute(
                select(RouteDecisionRecord)
                .where(RouteDecisionRecord.request_id == ctx.request_id)
                .order_by(desc(RouteDecisionRecord.plan_version))
                .limit(1)
            ).scalar_one_or_none()
            from_version = latest.plan_version if latest else 1
            to_version = from_version + 1
            if latest is not None:
                session.add(
                    RouteDecisionRecord(
                        id=new_id("route"),
                        request_id=latest.request_id,
                        trajectory_id=latest.trajectory_id,
                        query_profile_id=latest.query_profile_id,
                        capability_router_version=latest.capability_router_version,
                        selected_capabilities=latest.selected_capabilities,
                        restricted_capabilities=latest.restricted_capabilities,
                        capability_reason=latest.capability_reason,
                        execution_graph=capability_route.graph.to_dict(),
                        model_router_version=latest.model_router_version,
                        model_action=latest.model_action,
                        model_role=spec.new_model_role or latest.model_role,
                        require_verification=latest.require_verification,
                        human_approval_required=latest.human_approval_required,
                        model_reason=f"replanned: {spec.reason}",
                        expected_cost_class=latest.expected_cost_class,
                        expected_latency_class=latest.expected_latency_class,
                        plan_version=to_version,
                    )
                )
            session.add(
                ReplanRecord(
                    id=new_id("replan"),
                    request_id=ctx.request_id,
                    trajectory_id=ctx.trajectory_id,
                    trigger=spec.intervention_type.value,
                    from_plan_version=from_version,
                    to_plan_version=to_version,
                    reason=spec.reason,
                )
            )

    def _generation_handler(
        self, ctx: RequestContext, settings: Settings, query: str, role: str, captured: dict, graph: ExecutionGraph
    ):
        def handler(node) -> dict:
            prompt = self._build_generation_prompt(query, graph)
            try:
                result = self._invoke_model(ctx, settings, prompt, role=role)
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

    @staticmethod
    def _build_generation_prompt(query: str, graph: ExecutionGraph) -> str:
        """Milestone 5 fix (found during that milestone's mandatory
        architecture audit -- CRITICAL severity): through Milestone 4,
        the "generation" node called ``provider.generate(prompt=query)``
        with the raw query only, completely ignoring any SQL/RAG evidence
        retrieved by sibling nodes in the same graph. SQL/RAG ran, were
        evaluated (Grounding/Factuality), and were persisted -- but the
        model never actually saw them, so the RAG/SQL pipeline could not
        have been influencing real generated answers at all. This builds
        an evidence-augmented prompt from whichever SQL/RAG nodes
        actually completed; falls back to the bare query when neither
        ran (unchanged behavior for GENERAL/REASONING-only requests)."""
        import json

        context_blocks: list[str] = []
        for n in graph.nodes:
            if n.capability == "RAG" and n.status == NodeStatus.COMPLETED:
                for item in n.output_ref.get("evidence", []):
                    context_blocks.append(f"[{item['document']}]: {item['text']}")
            if n.capability == "SQL" and n.status == NodeStatus.COMPLETED:
                rows = n.output_ref.get("rows", [])
                if rows:
                    context_blocks.append(f"[SQL result -- {n.output_ref.get('template')}]: {json.dumps(rows[:10], default=str)}")

        if not context_blocks:
            return query

        context_text = "\n".join(context_blocks)
        return (
            "Answer the user's question using the context below where it is relevant. "
            "If the context does not fully answer the question, say so explicitly rather than guessing.\n\n"
            f"Context:\n{context_text}\n\nQuestion: {query}"
        )

    def _invoke_model(self, ctx: RequestContext, settings: Settings, prompt: str, role: str = "STRONG") -> dict:
        from controlplane.db.engine import session_scope
        from controlplane.db.models import ModelInvocationRecord

        invocation_id = new_id("inv")
        started_at = _utcnow()
        resolved_model = resolve_model_name(settings, role) or "unknown"

        try:
            provider = self._provider_factory(settings, role=role)
            result = provider.generate(prompt=prompt)
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
                    input_text=prompt,
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
    evaluation_suite=None,
    rag_capability=None,
    shadow_mode: bool = False,
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
        evaluation_suite=evaluation_suite,
        rag_capability=rag_capability,
        shadow_mode=shadow_mode,
    )
