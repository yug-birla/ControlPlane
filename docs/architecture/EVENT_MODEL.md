# ControlPlane.ai - Event Model

**Status:** Architecture Contract  
**Scope:** Runtime event semantics for ControlPlane.ai  
**Audience:** ControlPlane core, route/capability implementers, evaluators, intervention/replanner, observability, audit, and future infrastructure adapters

## 1. Purpose

This document defines the formal semantic contract for events in ControlPlane.ai.

The event model exists to let independently implemented capabilities communicate observations, outcomes, failures, evidence, and state transitions without becoming coupled to one another's control logic.

The governing runtime pattern is:

```text
Capability
    |
    v
  Event
    |
    v
Event Bus
    |
    v
ControlPlane Decision
    |
    v
Replanner / Intervention
    |
    v
New Execution Step
```

The Event Bus is a **communication mechanism**. It is not the ControlPlane brain. A route, capability, model, evaluator, or tool may report what happened, but it must not decide which other route should execute next. ControlPlane interprets the event in the context of the full execution state and decides whether to continue, retry, reroute, retrieve, verify, escalate, abstain, block, or replan.

This preserves the architecture's central separation:

```text
ControlPlane Core
= intelligence + state + policy + decision + replanning

Execution Graph
= what should happen

Event Bus
= what happened / what changed

Capability Fabric
= how capabilities are discovered and invoked
```

This is consistent with the existing architecture and agent instructions, which explicitly prohibit direct route-to-route replanning and require structured events for important state changes.

---

## 2. Event-Driven Architecture Rationale

ControlPlane is a dynamic execution system rather than a fixed route pipeline. The initial classification and plan are provisional. Execution can reveal that more data is required, retrieval is insufficient, models disagree, reasoning uncertainty is high, a tool is necessary, an action is unsafe, a budget is being consumed too quickly, or verification has failed.

A fixed pipeline would force these discoveries into hard-coded control flow. The event model instead makes discoveries first-class runtime facts.

### 2.1 What the architecture gains

- **Loose coupling:** capabilities emit normalized facts without knowing the next route.
- **Dynamic execution:** ControlPlane can change the execution graph when new evidence changes the situation.
- **Observability:** the same event stream can feed trajectory history, execution ledger, metrics, dashboards, and audit systems.
- **Failure isolation:** one capability can report failure without embedding recovery logic into every caller.
- **Auditability:** decisions can be reconstructed from events plus the authoritative execution state.
- **Extensibility:** new capability types can participate without changing the event semantics of existing capabilities.
- **Async scalability:** non-critical consumers can process events without blocking the user path.

The event model therefore supports the product's closed loop:

```text
Understand
   -> Plan
   -> Execute
   -> Observe
   -> Evaluate
   -> Decide
   -> Replan / Intervene
   -> Verify
   -> Respond
   -> Learn
```

### 2.2 Event Bus is not a workflow engine

The Event Bus must not contain business policy such as:

```text
RETRIEVAL_INSUFFICIENT -> always call SQL
```

or:

```text
MODEL_FAILURE -> always call Model B
```

Those are ControlPlane decisions. The event only states the observed condition. The ControlPlane combines that condition with trajectory state, plan version, evidence, policy, risk, confidence, cost, latency, permissions, and available capabilities before deciding what to do.

---

## 3. Event vs Command vs State Update

These concepts must remain distinct.

| Concept | Meaning | Typical producer | Intended consumer | Control semantics |
|---|---|---|---|---|
| **Event** | A fact that something happened or was observed | Capability, evaluator, ControlPlane subsystem | ControlPlane, history, ledger, observability, evaluators | Describes reality; does not instruct another route |
| **Command** | An explicit instruction to perform an operation | ControlPlane | Executor, capability, intervention engine | Authoritative instruction |
| **State update** | A mutation of the current execution state | ControlPlane state manager, normalized capability result handler | Execution state / stores | Changes authoritative state |

Examples:

```text
Event:
RETRIEVAL_INSUFFICIENT

Command:
RUN_RETRIEVAL { strategy: "hybrid_v2" }

State update:
current_step = "retrieval_v2"
plan_version = 3
```

A capability may emit an event and return a normalized result. It does not emit a command to another capability as a substitute for ControlPlane decision-making.

---

## 4. Event Lifecycle

Every event follows the conceptual lifecycle below:

```text
1. Observe
   capability/evaluator/control component detects a fact
        |
2. Construct
   normalize the fact into the canonical event envelope
        |
3. Validate
   schema, identifiers, version, severity, timestamps, source
        |
4. Publish
   event is handed to the event transport mechanism
        |
5. Persist
   event becomes part of execution history/audit where required
        |
6. Consume
   ControlPlane and/or secondary consumers receive the event
        |
7. Interpret
   ControlPlane evaluates the event against current execution state
        |
8. Decide
   continue, mutate state, intervene, replan, escalate, abstain, etc.
        |
9. Act
   a new command/plan version/execution step may be created
        |
10. Verify
   outcome of intervention or continuation is evaluated
        |
11. Record
   resulting events and state changes are persisted
```

An event may therefore be **important without being actionable**. Informational events can be persisted and consumed for traceability without changing the current plan.

---

## 5. Canonical Event Schema

The canonical event envelope is transport-neutral. Infrastructure adapters may serialize it as JSON, Protobuf, or another format later, but the semantic fields below remain stable.

Conceptual schema:

```json
{
  "event_id": "evt_01J...",
  "event_type": "RETRIEVAL_INSUFFICIENT",
  "event_version": 1,

  "request_id": "req_01J...",
  "trace_id": "trc_01J...",
  "trajectory_id": "traj_01J...",
  "plan_id": "plan_01J...",
  "plan_version": 2,
  "step_id": "step_04",

  "source": {
    "kind": "retrieval",
    "component_id": "enterprise_rag",
    "capability_id": "enterprise_rag",
    "instance_id": "worker_17"
  },

  "severity": "warning",
  "confidence": 0.93,

  "occurred_at": "2026-08-25T14:30:00Z",
  "observed_at": "2026-08-25T14:30:00.140Z",
  "published_at": "2026-08-25T14:30:00.155Z",

  "correlation_id": "corr_01J...",
  "causation_id": "evt_01J...",
  "sequence_no": 41,

  "evidence": [
    {
      "evidence_id": "ev_123",
      "kind": "retrieval_metric",
      "reference": "retrieval_run_456",
      "summary": "Top-k evidence did not meet adequacy threshold"
    }
  ],

  "payload": {
    "adequacy_score": 0.31,
    "required_threshold": 0.70,
    "missing_data_classes": ["quarterly_revenue"]
  },

  "deduplication_key": "retrieval_run_456:insufficient",
  "producer_schema": "retrieval-event-v1"
}
```

### 5.1 Required envelope fields

The following fields are required for every event:

| Field | Requirement | Purpose |
|---|---|---|
| `event_id` | Required | Globally unique identity of this event occurrence |
| `event_type` | Required | Stable taxonomy name |
| `event_version` | Required | Version of the event contract |
| `request_id` | Required | User/request scope |
| `trace_id` | Required | End-to-end observability scope |
| `trajectory_id` | Required for active execution | Identifies the evolving execution trajectory |
| `source` | Required | Identifies the producer |
| `severity` | Required | Operational/policy importance |
| `confidence` | Required when inferential | Confidence in the event assertion |
| `occurred_at` | Required | When the underlying fact occurred |
| `published_at` | Required | When the event was emitted to the bus |
| `payload` | Required | Type-specific event data, possibly empty for pure lifecycle events |

`plan_id`, `plan_version`, `step_id`, `correlation_id`, `causation_id`, `sequence_no`, and `evidence` are required when applicable and should be populated for execution events whenever known.

---

## 6. Required Event Metadata

### 6.1 `event_id`

Identifies one event occurrence. Consumers must never assume delivery is exactly once. `event_id` is the primary key for duplicate detection.

### 6.2 `event_type`

Stable semantic name from the canonical taxonomy. Event type names must not be reused for materially different meanings.

### 6.3 `event_version`

Version of the event's public contract. Schema evolution must be additive or explicitly versioned; meaning must not silently change under an existing version.

### 6.4 `request_id`

Stable identifier for the user/request lifecycle. Multiple trajectories may exist under a request when the architecture supports retries, resumed workflows, or continuation, but the request remains the top-level business scope.

### 6.5 `trace_id`

End-to-end observability identifier. It connects application ingress, internal processing, capability calls, events, evaluations, interventions, and final response telemetry.

### 6.6 `trajectory_id`

Identifier for the specific execution trajectory being governed. It is the key for trajectory-level reasoning, particularly for agentic and multi-step execution where risk depends on cumulative state, permissions, data exposure, and actions.

### 6.7 `plan_id` and `plan_version`

`plan_id` identifies the logical execution plan. `plan_version` identifies the concrete strategy active when the event occurred or was emitted.

A replan creates a new plan version. Historical events keep the plan version under which they were generated; they must not be rewritten to the new version.

### 6.8 `step_id`

Identifies the execution-graph step associated with the event, when applicable. It is essential for reconstructing which node observed or caused the event.

### 6.9 `source`

Events must identify the semantic producer, not merely an infrastructure worker.

Preferred structure:

```text
source.kind
source.component_id
source.capability_id   (when applicable)
source.instance_id     (optional operational detail)
```

Examples of `source.kind`:

```text
controlplane
route
model
retrieval
tool
agent
evaluator
policy
intervention
human
system
```

### 6.10 Severity

Severity communicates operational and governance importance, not model confidence.

Canonical levels:

```text
info
notice
warning
high
critical
```

Severity is context-sensitive. For example, a model disagreement in a low-impact task may be `warning`, while the same disagreement in a high-impact decision-support trajectory may be `high` or `critical`.

### 6.11 Confidence

Confidence represents the producer's confidence that the event assertion is correct, not the confidence of the final answer.

Use a normalized value in `[0, 1]` where a numeric estimate is justified. If the producer cannot justify a calibrated numeric value, it should use a coarse semantic confidence representation at the internal layer rather than inventing precision.

Confidence never overrides severity, policy, authorization, or explicit safety constraints.

### 6.12 Evidence references

Important events must be evidence-backed whenever the event is an inference, evaluation, risk finding, or other non-trivial assertion.

Evidence references should identify:

```text
evidence_id
kind
reference/location
summary
optional score/freshness
```

The event stores a reference to evidence; it need not embed large documents, model outputs, or raw payloads directly.

### 6.13 Timestamps

Use separate timestamps for different semantics:

- `occurred_at` - when the underlying event happened.
- `observed_at` - when the producer observed or established it.
- `published_at` - when the event was published.
- `processed_at` - optional consumer-side timestamp.

This distinction is required for latency diagnostics and asynchronous processing analysis.

### 6.14 Correlation and causation

`correlation_id` links a logical group of related events, such as all events associated with one intervention attempt or one execution branch.

`causation_id` points to the event that directly caused the current event to be emitted, when applicable.

Example:

```text
MODEL_CALLED (event A)
      |
      +--> MODEL_DISAGREEMENT (event B)
                  |
                  +--> REPLAN_TRIGGERED (event C)
```

`B.causation_id = A.event_id` and `C.causation_id = B.event_id`.

Causation is not the same as business correlation. An event may be correlated with many events but have one immediate causation edge.

---

## 7. Event Source and Producer Contract

Any component may publish an event only for a fact it owns or has directly established.

### Producer rules

1. Publish facts, observations, outcomes, and explicit state-relevant discoveries.
2. Do not publish hidden control instructions disguised as events.
3. Do not call another route solely because an event suggests it may be needed.
4. Include sufficient evidence for evaluative or risk-sensitive assertions.
5. Preserve the active `request_id`, `trace_id`, `trajectory_id`, and `plan_version` context.
6. Use stable event types and schema versions.
7. Publish once per meaningful occurrence; consumers must still tolerate duplicates.

Example of **correct** route behavior:

```text
RAG capability
   |
   +--> RETRIEVAL_INSUFFICIENT
               |
               v
          Event Bus
               |
               v
          ControlPlane
               |
               +--> inspect current evidence/policy/budget
               +--> decide alternate retrieval
               +--> create plan v3
               +--> execute new step
```

Example of **incorrect** behavior:

```text
RAG capability
   |
   +--> SQL route directly
```

---

## 8. Event Persistence

Events are part of execution history, not merely transient logs.

Persistence has two conceptual destinations:

```text
Event History / Trajectory Store
= reconstructable execution history

Execution Ledger
= append-only record of consequential facts
```

The Trajectory Store supports recovery, replay, inspection, and replanning. The Execution Ledger records consequential facts such as data accessed, permissions used, models invoked, tools called, actions proposed/authorized/executed, external destinations, policy decisions, interventions, and human overrides.

Not every informational event must become a durable ledger entry, but every event that is necessary to explain a control decision, intervention, safety outcome, authorization outcome, or externally consequential action must remain reconstructable.

Historical events are immutable facts. A corrected interpretation should be represented as a new event, not by editing the old event.

---

## 9. Event Ordering Assumptions

The event model does **not** require a single global total order across the whole system.

The architecture assumes:

- events may arrive out of order across unrelated trajectories;
- consumers must not derive global causality from arrival order;
- ordering that matters must be represented explicitly through `sequence_no`, `causation_id`, timestamps, and plan/step identifiers;
- the strongest practical ordering guarantee is normally per `trajectory_id` and, where needed, per execution step/branch;
- parallel execution may legitimately produce concurrent events;
- late events remain valid historical facts but must be interpreted against the state that was current when they were observed.

When a decision depends on ordering, ControlPlane should reason over the trajectory/event history rather than relying on transport delivery order alone.

---

## 10. Duplicate Events and Idempotency

At-least-once delivery must be assumed unless an infrastructure implementation can prove a stronger guarantee. Event consumers therefore must be idempotent.

### 10.1 Event identity

`event_id` identifies a single event occurrence.

### 10.2 Deduplication key

Some event types should also expose a semantic `deduplication_key`, for example:

```text
<capability_run_id>:<condition>
<tool_call_id>:<failure_code>
<evaluation_id>:<evaluation_type>
```

This is useful when two producer executions independently report the same underlying condition.

### 10.3 Consumer behavior

A consumer should:

```text
receive event
  |
  +--> already processed event_id? -> ignore/replay-safe response
  |
  +--> new event -> process
```

For state-changing reactions, prefer conditional state transitions keyed by trajectory and expected plan version so that duplicate delivery cannot apply an intervention twice.

Example:

```text
Current plan_version = 4

Event: VERIFICATION_FAILED
Decision: insert verification repair step

Apply only if plan_version still = 4.
If already advanced to v5, the duplicate event must not create v6 again.
```

---

## 11. Retries

Retries are transport/execution mechanics, not implicit policy decisions.

### 11.1 Safe retry

A consumer may retry event processing when failure is transient and the operation is idempotent.

### 11.2 Bounded retries

Event processing and event-triggered recovery must have explicit limits. No path may recurse indefinitely:

```text
evaluation
 -> intervention
 -> replan
 -> evaluation
 -> intervention
 -> ...
```

The execution state must track retry/replan counts where relevant, and decisions must remain within cost, latency, risk, and policy budgets.

### 11.3 Retry failure

After bounded retry attempts, the consumer should produce an explicit failure event rather than silently dropping the event. The ControlPlane then decides whether to degrade, continue, escalate, or terminate.

---

## 12. Dead-Letter / Failure Behavior

A dead-letter mechanism is an infrastructure concern, but its semantic behavior is fixed here.

An event may be routed to a dead-letter/failure path when:

- schema validation repeatedly fails;
- the event version is unsupported and cannot be safely downgraded;
- a required dependency remains unavailable after bounded retries;
- consumer processing repeatedly fails;
- the event cannot be associated with a valid execution context;
- the event violates security/integrity checks.

A dead-lettered event is **not equivalent to no event**. It must remain observable and auditable.

The failure path should preserve the original event, failure reason, retry count, and relevant identifiers. The ControlPlane may need to degrade or escalate if the missing event could affect safe execution.

The specific technology used for the dead-letter path is intentionally outside this contract.

---

## 13. Synchronous vs Asynchronous Events

The classification is based on whether the event must be interpreted before the current user-visible execution can safely continue.

### 13.1 Synchronous / critical-path events

These are events that can immediately affect the next execution step or authorization decision.

Typical examples:

```text
DATA_UNAVAILABLE
RETRIEVAL_INSUFFICIENT
EVIDENCE_CONFLICT
MODEL_FAILURE
HIGH_REASONING_UNCERTAINTY
HIGH_ACTION_RISK
PERMISSION_ESCALATION
PII_DETECTED
PRIVACY_RISK
SAFETY_RISK
VERIFICATION_FAILED
HUMAN_REVIEW_REQUIRED
```

The event may block continuation until ControlPlane decides what happens next.

### 13.2 Asynchronous events

These are events useful for observability, analytics, evaluation, learning, or historical analysis without being required before a safe user response.

Examples:

```text
COST_BUDGET_WARNING (when non-blocking)
LATENCY_BUDGET_WARNING (when non-blocking)
ROUTE_COMPLETED
EVALUATION_COMPLETED (when post-response)
behavioral telemetry
route statistics
benchmarking signals
```

The same event type may be critical or informational depending on policy and trajectory state. Classification is therefore contextual rather than permanently hard-coded.

---

# 14. Canonical Event Taxonomy

The following taxonomy is the canonical starting set for ControlPlane. Producers may emit additional events only when a stable semantic requirement exists; new event types should not be created merely as aliases for existing ones.

## 14.1 Event summary

| Event | Primary producer | State change? | Replan eligible? | Default severity | Likely consumers |
|---|---|---:|---:|---|---|
| `QUERY_RECEIVED` | Gateway / ControlPlane | Yes | Yes, initial planning | info | Query Intelligence, trace, history |
| `QUERY_RECLASSIFIED` | Query Intelligence / evaluator | Yes | Yes | notice / warning | ControlPlane, planner, history |
| `PLAN_CREATED` | Planner | Yes | No | info | Execution Graph, history, dashboard |
| `PLAN_UPDATED` | Replanner / ControlPlane | Yes | Yes, represents the replan result | notice | Execution Graph, trace, ledger |
| `ROUTE_STARTED` | Execution Graph / route | Yes | No | info | trace, dashboard, ledger |
| `ROUTE_COMPLETED` | Route / capability | Yes | Contextual | info | state, trace, evaluation |
| `DATA_REQUIRED` | Capability / evaluator | Yes | Yes | warning | ControlPlane, planner, data capability registry |
| `DATA_UNAVAILABLE` | Data capability | Yes | Yes | high | ControlPlane, planner, policy, audit |
| `RETRIEVAL_INSUFFICIENT` | Retrieval capability / evaluator | Yes | Yes | warning | ControlPlane, retrieval planner, verifier |
| `EVIDENCE_CONFLICT` | Evidence merge / evaluator | Yes | Yes | high | ControlPlane, verifier, planner |
| `MODEL_CALLED` | Model capability / executor | Yes | Usually no | info | trace, cost, latency, history |
| `MODEL_FAILURE` | Model capability | Yes | Yes | high | ControlPlane, fallback planner, reliability |
| `MODEL_DISAGREEMENT` | Model/evaluation layer | Yes | Yes | warning / high | ControlPlane, verifier, planner |
| `HIGH_REASONING_UNCERTAINTY` | Model/evaluator | Yes | Yes | high | ControlPlane, reasoning planner, verifier |
| `TOOL_CALLED` | Tool executor | Yes | Usually no | info | ledger, trace, action monitor |
| `TOOL_FAILURE` | Tool executor | Yes | Yes | high | ControlPlane, recovery, audit |
| `HIGH_ACTION_RISK` | Policy / action-risk evaluator | Yes | Yes | critical for consequential action | ControlPlane, intervention, human review |
| `PERMISSION_ESCALATION` | Policy / authorization layer | Yes | Yes | high | ControlPlane, policy, human review, audit |
| `PII_DETECTED` | Privacy / PII evaluator | Yes | Yes | high | ControlPlane, privacy, redaction, audit |
| `PRIVACY_RISK` | Privacy evaluator | Yes | Yes | high | ControlPlane, policy, intervention |
| `SAFETY_RISK` | Safety evaluator | Yes | Yes | high / critical | ControlPlane, policy, intervention, human review |
| `BIAS_RISK` | Bias evaluator | Yes | Contextual | warning / high | ControlPlane, evaluation, policy |
| `BEHAVIORAL_DRIFT_HIGH` | Drift monitor | Yes | Yes | high | ControlPlane, intervention, audit |
| `EVALUATION_COMPLETED` | Evaluator | Yes | Contextual | info / notice | ControlPlane, history, dashboard |
| `VERIFICATION_FAILED` | Verifier | Yes | Yes | high | ControlPlane, replanner, intervention |
| `INTERVENTION_TRIGGERED` | ControlPlane / intervention engine | Yes | No direct route selection | notice / high | trajectory store, ledger, dashboard |
| `REPLAN_TRIGGERED` | ControlPlane decision layer | Yes | Yes, by definition | notice / high | planner, execution graph, history |
| `HUMAN_REVIEW_REQUIRED` | ControlPlane / policy | Yes | Yes | high / critical | human-review system, audit, dashboard |
| `FINAL_RESPONSE_GENERATED` | Response layer | Yes | Usually no; may still cause post-response evaluation | info | response audit, trust, analytics |

The `severity` shown above is a default. Actual severity must be determined in context using impact, risk, policy, confidence, and trajectory state.

---

# 15. Event Definitions and Payload Concepts

The following sections define the important events requested by the architecture contract. Payloads are conceptual, not frozen implementation schemas.

## 15.1 `QUERY_RECEIVED`

**Producer:** API Gateway / ControlPlane ingress  
**Meaning:** A request entered the ControlPlane execution domain.  
**State change:** Yes; creates request/trace/trajectory context.  
**Can trigger replanning:** Yes in the broad sense of initiating initial planning; it is not a recovery event.  
**Likely consumers:** Query Intelligence, planner, trace/history, policy initialization.  
**Default severity:** `info`.

Payload concept:

```text
query_id
application_id
session/conversation context
policy context
initial budgets
input characteristics
```

## 15.2 `QUERY_RECLASSIFIED`

**Producer:** Query Intelligence, evaluator, or ControlPlane decision layer  
**Meaning:** The provisional Query Fingerprint changed because new information altered the task interpretation.  
**State change:** Yes; updates query profile.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, planner, policy, history.  
**Default severity:** `notice` or `warning`.

Payload concept:

```text
previous_profile
new_profile
changed_dimensions
reason
evidence_refs
```

## 15.3 `PLAN_CREATED`

**Producer:** Planner / ControlPlane  
**Meaning:** An initial executable strategy was created.  
**State change:** Yes; creates a plan version.  
**Can trigger replanning:** No; it establishes the plan.  
**Likely consumers:** Execution Graph, trajectory store, dashboard.  
**Default severity:** `info`.

Payload concept:

```text
plan_id
plan_version=1
steps
dependencies
parallel_groups
verification_level
budgets
policy_context
```

## 15.4 `PLAN_UPDATED`

**Producer:** ControlPlane / Replanner  
**Meaning:** The current execution strategy changed and a new plan version became authoritative.  
**State change:** Yes.  
**Can trigger replanning:** It is the result of a replan, not a request for one.  
**Likely consumers:** Execution Graph, trajectory store, ledger, dashboard.  
**Default severity:** `notice` or `high` depending on impact.

Payload concept:

```text
plan_id
previous_plan_version
new_plan_version
change_set
trigger_event_id
rationale
budget_impact
```

## 15.5 `ROUTE_STARTED`

**Producer:** Execution Graph / route executor  
**Meaning:** A planned execution step started.  
**State change:** Yes; step becomes active.  
**Can trigger replanning:** No.  
**Likely consumers:** Trace, trajectory store, cost/latency monitor.  
**Default severity:** `info`.

Payload concept:

```text
route_id
step_id
capability_id
start_reason
```

## 15.6 `ROUTE_COMPLETED`

**Producer:** Route executor / capability  
**Meaning:** A route or step completed with a normalized result/status.  
**State change:** Yes.  
**Can trigger replanning:** Contextual; completion itself normally does not, but its result may cause another event.  
**Likely consumers:** Execution State, evaluator, trace, ledger.  
**Default severity:** `info`.

Payload concept:

```text
step_id
status
result_reference
latency
cost
evidence_refs
```

## 15.7 `DATA_REQUIRED`

**Producer:** Capability, evaluator, or ControlPlane subsystem that discovers a missing data class  
**Meaning:** The current path cannot adequately continue without additional data.  
**State change:** Yes; records an unmet data requirement.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, planner, data capability registry, policy.  
**Default severity:** `warning`.

Payload concept:

```text
required_data_class
authority_requirement
sensitivity
reason
current_step
```

## 15.8 `DATA_UNAVAILABLE`

**Producer:** SQL/RAG/memory/web/API data capability  
**Meaning:** Required data was requested but cannot be obtained under current availability or authorization.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, fallback planner, policy, audit.  
**Default severity:** `high`.

Payload concept:

```text
resource_type
resource_reference
failure_reason
availability_state
authorization_state
```

## 15.9 `RETRIEVAL_INSUFFICIENT`

**Producer:** Retrieval capability or retrieval evaluator  
**Meaning:** Retrieved evidence does not meet adequacy criteria for the task.  
**State change:** Yes; evidence state is insufficient.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, retrieval planner, verifier.  
**Default severity:** `warning`.

Payload concept:

```text
retrieval_run_id
adequacy_score
threshold
missing_topics
source_quality
freshness
```

## 15.10 `EVIDENCE_CONFLICT`

**Producer:** Evidence merger, verifier, evaluator  
**Meaning:** Two or more evidence sources provide materially inconsistent claims.  
**State change:** Yes; risk/confidence/evidence state changes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, verifier, retrieval planner, policy, final trust report.  
**Default severity:** `high`.

Payload concept:

```text
claim_id
conflicting_evidence_refs
conflict_type
source_authority
freshness_difference
```

## 15.11 `MODEL_CALLED`

**Producer:** Model capability executor  
**Meaning:** A model invocation was initiated/completed for a particular execution step.  
**State change:** Yes; model call becomes part of trajectory/cost/latency state.  
**Can trigger replanning:** Normally no.  
**Likely consumers:** Trace, cost monitor, latency monitor, trajectory ledger.  
**Default severity:** `info`.

Payload concept:

```text
model_id
provider_class
task_class
tokens_in_estimate
tokens_out_estimate
started_at
completed_at
```

## 15.12 `MODEL_FAILURE`

**Producer:** Model capability / provider adapter  
**Meaning:** A model invocation failed or produced a failure status that makes the intended step incomplete.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, fallback planner, reliability monitor, audit.  
**Default severity:** `high`.

Payload concept:

```text
model_id
failure_class
provider_status
retryable
attempt_no
partial_output_reference
```

## 15.13 `MODEL_DISAGREEMENT`

**Producer:** Model ensemble / evaluator  
**Meaning:** Independent model outputs materially disagree on a claim, decision, or conclusion relevant to the task.  
**State change:** Yes; confidence/risk state changes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, verifier, reasoning planner, trust layer.  
**Default severity:** `warning` or `high`.

Payload concept:

```text
model_outputs[]
disputed_claims
agreement_measure
confidence_by_model
evidence_refs
```

## 15.14 `HIGH_REASONING_UNCERTAINTY`

**Producer:** Model/evaluator  
**Meaning:** The reasoning task is judged too uncertain for the current plan's confidence/risk requirements.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, reasoning planner, verifier.  
**Default severity:** `high`.

Payload concept:

```text
uncertainty_signal
threshold
reasoning_class
model_id
evidence_refs
```

## 15.15 `TOOL_CALLED`

**Producer:** Tool executor / agent execution layer  
**Meaning:** A tool invocation was performed or accepted for execution under ControlPlane authorization.  
**State change:** Yes; tool use enters the trajectory and ledger.  
**Can trigger replanning:** Normally no, but the result may cause another event.  
**Likely consumers:** Execution Ledger, action monitor, trace, policy.  
**Default severity:** `info`.

Payload concept:

```text
tool_id
tool_call_id
authorization_reference
input_reference
external_destination
reversibility
```

## 15.16 `TOOL_FAILURE`

**Producer:** Tool executor / integration layer  
**Meaning:** A required or attempted tool call failed.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, recovery, audit, policy.  
**Default severity:** `high`.

Payload concept:

```text
tool_id
tool_call_id
failure_class
retryable
side_effect_status
partial_effect_reference
```

## 15.17 `HIGH_ACTION_RISK`

**Producer:** Action-risk evaluator / policy engine  
**Meaning:** A proposed or in-progress action exceeds the risk threshold permitted by the current policy and trajectory state.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, intervention engine, human review, audit.  
**Default severity:** `critical` for consequential external actions.

Payload concept:

```text
action_class
impact
reversibility
external_destination
risk_factors
risk_score_or_band
authorization_context
```

## 15.18 `PERMISSION_ESCALATION`

**Producer:** Authorization / policy layer  
**Meaning:** The next step requires permissions beyond the current authorization context.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, policy, human review, audit.  
**Default severity:** `high`.

Payload concept:

```text
current_permission_set
required_permission
resource
reason
approval_policy
```

## 15.19 `PII_DETECTED`

**Producer:** Privacy/PII evaluator  
**Meaning:** Potentially identifying or sensitive personal information was detected in input, retrieved data, model output, tool payload, or external destination.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, privacy policy, redaction, audit, human review.  
**Default severity:** `high`.

Payload concept:

```text
location
pii_category
detection_confidence
handling_requirement
data_flow_reference
```

## 15.20 `PRIVACY_RISK`

**Producer:** Privacy evaluator / policy engine  
**Meaning:** The current trajectory creates a privacy risk even when no single PII detection alone is sufficient to explain it.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, policy, intervention, audit.  
**Default severity:** `high`.

Payload concept:

```text
risk_dimension
exposure_path
affected_data
policy_reference
recommended_handling
```

## 15.21 `SAFETY_RISK`

**Producer:** Safety evaluator / policy layer  
**Meaning:** The current content, trajectory, or proposed behavior presents a safety concern.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, intervention, policy, human review.  
**Default severity:** `high` or `critical`.

Payload concept:

```text
safety_category
evidence_refs
risk_context
policy_reference
```

## 15.22 `BIAS_RISK`

**Producer:** Bias evaluator  
**Meaning:** An output or decision exhibits a bias signal that may be material under the active policy or use case.  
**State change:** Yes.  
**Can trigger replanning:** Contextual; yes when bias affects task suitability or policy compliance.  
**Likely consumers:** ControlPlane, evaluator, policy, trust layer.  
**Default severity:** `warning` or `high`.

Payload concept:

```text
bias_dimension
population_or_group_context
metric
threshold
evidence_refs
```

## 15.23 `BEHAVIORAL_DRIFT_HIGH`

**Producer:** Behavioral Drift Monitor  
**Meaning:** Actual trajectory behavior deviates materially from the expected trajectory.  
**State change:** Yes; drift state changes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, intervention engine, policy, audit.  
**Default severity:** `high`.

Payload concept:

```text
drift_score
baseline_reference
signals
unexpected_tool_velocity
unexpected_data_source
unexpected_permission_use
unexpected_external_destination
```

The drift score should remain interpretable and bounded. It is a decision signal, not a standalone policy engine.

## 15.24 `EVALUATION_COMPLETED`

**Producer:** Evaluator  
**Meaning:** An evaluation completed and produced structured findings.  
**State change:** Yes; evaluation state is recorded.  
**Can trigger replanning:** Contextual. A failing or materially negative result can lead to a decision; the event itself does not automatically mean replan.  
**Likely consumers:** ControlPlane, dashboard, history, learning.  
**Default severity:** `info` or `notice`.

Payload concept:

```text
evaluator_type
scores
confidence
issues
evidence_refs
recommended_action
```

## 15.25 `VERIFICATION_FAILED`

**Producer:** Verification layer  
**Meaning:** The response/action does not satisfy the required verification level or policy.  
**State change:** Yes.  
**Can trigger replanning:** Yes.  
**Likely consumers:** ControlPlane, replanner, intervention engine, trust layer.  
**Default severity:** `high`.

Payload concept:

```text
verification_type
failed_checks
thresholds
evidence_refs
current_trust_state
```

## 15.26 `INTERVENTION_TRIGGERED`

**Producer:** ControlPlane decision layer / intervention engine  
**Meaning:** ControlPlane selected and initiated a bounded intervention.  
**State change:** Yes.  
**Can trigger replanning:** Not by itself; the intervention may lead to a replan or continuation event.  
**Likely consumers:** Trajectory Store, Execution Ledger, dashboard, audit, learning.  
**Default severity:** `notice` or `high`.

Payload concept:

```text
intervention_type
trigger_event_id
reason
bounds
previous_step
expected_outcome
```

Examples of intervention type:

```text
RETRY
REGENERATE
REROUTE
RETRIEVE
CHANGE_RETRIEVAL
CHANGE_MODEL
INCREASE_REASONING
VERIFY
REPAIR
REDACT
ASK_CLARIFICATION
ABSTAIN
ESCALATE
HUMAN_REVIEW
BLOCK
ABORT
```

## 15.27 `REPLAN_TRIGGERED`

**Producer:** ControlPlane Decision Engine  
**Meaning:** ControlPlane determined that the current execution plan is no longer the best or safest strategy under the new state.  
**State change:** Yes.  
**Can trigger replanning:** Yes, by definition it enters the replanning path; the actual plan replacement is recorded through `PLAN_UPDATED`.  
**Likely consumers:** Replanner, trajectory store, execution graph, audit.  
**Default severity:** `notice` or `high`.

Payload concept:

```text
trigger_event_id
reason_code
old_plan_version
candidate_changes
policy/budget constraints
```

## 15.28 `HUMAN_REVIEW_REQUIRED`

**Producer:** ControlPlane / policy / action-risk evaluator  
**Meaning:** Automated execution must pause or escalate because policy, uncertainty, impact, or authorization requires human judgment.  
**State change:** Yes; workflow enters human-review state.  
**Can trigger replanning:** Yes.  
**Likely consumers:** Human-review system, ControlPlane, audit, dashboard.  
**Default severity:** `high` or `critical`.

Payload concept:

```text
review_reason
review_scope
required_role
blocked_steps
required_evidence
expiry_or_timeout
```

## 15.29 `FINAL_RESPONSE_GENERATED`

**Producer:** Response layer / ControlPlane  
**Meaning:** A candidate or final user-visible response was generated under a particular trajectory and plan version.  
**State change:** Yes; response becomes part of final execution state.  
**Can trigger replanning:** Normally no, but post-response evaluation may still emit new events if the response has not yet been released.  
**Likely consumers:** trust layer, audit, analytics, final-response gateway.  
**Default severity:** `info`.

Payload concept:

```text
response_reference
final_status
trust_state
evidence_summary
limitations
plan_version
```

---

# 16. Additional Event Classes

The canonical taxonomy above should be complemented by event families that share common envelope semantics.

## 16.1 Agent and tool events

Agentic workflows must be represented at trajectory level. Tool events should capture:

```text
action proposed
permission context
authorization decision
tool called
tool result
tool failure
external destination
side-effect status
post-action verification
```

A model/agent is never the final authorization authority merely because it generated a tool call.

## 16.2 Model events

Model events should distinguish:

```text
MODEL_CALLED
MODEL_FAILURE
MODEL_DISAGREEMENT
HIGH_REASONING_UNCERTAINTY
```

Quality, uncertainty, latency, token usage, and cost should remain structured rather than hidden in logs.

## 16.3 Retrieval events

Retrieval events should preserve evidence adequacy and lineage:

```text
retrieval requested
retrieval completed
retrieval insufficient
source unavailable
source conflict
freshness problem
```

The retrieval layer reports the evidence state. ControlPlane decides whether to change retrieval, add a source, invoke enterprise data, verify differently, or abstain.

## 16.4 Evaluation events

Evaluators should return structured results such as:

```text
score
confidence
issues
evidence
recommended_action
```

The evaluator does not directly invoke an intervention merely because its recommendation says so. The recommendation is an input to ControlPlane decision-making.

## 16.5 Intervention events

Intervention events must document:

```text
trigger
intervention type
bounds
policy context
plan version
expected result
actual result
```

This makes self-healing explainable and allows later evaluation of whether the intervention helped.

## 16.6 Human-review events

Human-review events must preserve:

```text
why review was required
who/what role is required
what is blocked
what evidence is available
what decision was made
who made it
when it was made
```

Human override is a first-class audit fact.

## 16.7 Cost and latency events

Cost and latency should be represented as execution constraints, not just dashboard metrics.

Typical events include:

```text
LATENCY_BUDGET_WARNING
COST_BUDGET_WARNING
LATENCY_BUDGET_EXCEEDED
COST_BUDGET_EXCEEDED
```

Only the first two are required by the current canonical set; additional events may be introduced when a distinct semantic decision boundary exists.

A budget warning should identify:

```text
budget type
budget limit
used amount
projected amount
remaining budget
causing step(s)
```

Whether a warning triggers a replan depends on policy and projected impact.

---

## 17. Events That Can Trigger Replanning

Replanning is a ControlPlane decision, but the following events are canonical replan candidates:

```text
QUERY_RECLASSIFIED
DATA_REQUIRED
DATA_UNAVAILABLE
RETRIEVAL_INSUFFICIENT
EVIDENCE_CONFLICT
MODEL_FAILURE
MODEL_DISAGREEMENT
HIGH_REASONING_UNCERTAINTY
TOOL_FAILURE
HIGH_ACTION_RISK
PERMISSION_ESCALATION
PII_DETECTED
PRIVACY_RISK
SAFETY_RISK
BEHAVIORAL_DRIFT_HIGH
VERIFICATION_FAILED
HUMAN_REVIEW_REQUIRED
```

Additional evaluative events such as `EVALUATION_COMPLETED` can also lead to replanning when their result materially changes the execution state.

The relationship is:

```text
Event
  |
  v
ControlPlane interpretation
  |
  +--> no action
  +--> state update
  +--> intervention
  +--> human review
  +--> replan
  +--> terminate / abstain
```

No event type has an automatic universal replan behavior.

---

## 18. Informational-Only Events

Events may be informational when they document normal execution rather than a condition requiring a decision.

Typical examples:

```text
QUERY_RECEIVED
PLAN_CREATED
ROUTE_STARTED
ROUTE_COMPLETED
MODEL_CALLED
TOOL_CALLED
FINAL_RESPONSE_GENERATED
```

`EVALUATION_COMPLETED` is often informational but may become decision-relevant based on its payload.

Informational does not mean disposable. Events required for traceability, audit, cost accounting, or trajectory reconstruction must still be retained according to the persistence policy.

---

## 19. Security-Sensitive Events

The following events must be treated as security/governance-sensitive and should receive stronger persistence, access-control, and audit guarantees:

```text
HIGH_ACTION_RISK
PERMISSION_ESCALATION
PII_DETECTED
PRIVACY_RISK
SAFETY_RISK
HUMAN_REVIEW_REQUIRED
TOOL_CALLED             (when externally consequential)
TOOL_FAILURE            (when side effects may have occurred)
BEHAVIORAL_DRIFT_HIGH
```

For security-sensitive events:

- preserve immutable event history;
- restrict payload visibility according to data sensitivity;
- avoid embedding secrets, raw credentials, or unnecessary PII;
- preserve authorization and policy references;
- preserve external destinations for consequential actions;
- retain enough evidence to reconstruct the decision without copying sensitive raw data unnecessarily.

---

# 20. Event Versioning and Backward Compatibility

Event contracts must evolve without silently changing existing semantics.

## 20.1 Compatibility rules

Prefer additive changes:

```text
v1:
{ event_type, request_id, payload.foo }

v1 compatible extension:
{ event_type, request_id, payload.foo, payload.bar }
```

A breaking semantic or structural change requires a new event version.

Examples of breaking changes:

- changing the meaning of `severity`;
- changing `payload.foo` from a scalar to a semantically incompatible object;
- removing a field required by existing consumers;
- changing an event from an observation to a command;
- changing the event's causal semantics.

## 20.2 Producer compatibility

Producers should be able to emit a currently supported event version during a rolling upgrade.

## 20.3 Consumer compatibility

Consumers should ignore unknown optional fields and should fail closed or safely degrade when required fields are missing or an unsupported version affects a governance-critical decision.

## 20.4 Event type stability

Do not rename an event merely for stylistic reasons. Stable event names are important for historical analytics, audit queries, and dashboards.

---

# 21. Observability Requirements

The event model is part of the observability contract.

Every meaningful execution should permit an operator or developer to answer:

```text
What happened?
Why did it happen?
Which route/step was active?
Which plan version was active?
What evidence supported it?
What failed?
What triggered intervention?
What changed?
Did the intervention help?
What did it cost?
How much latency did it add?
Was human review involved?
What was the final outcome?
```

Minimum traceable fields across the event/trajectory system should include:

```text
request_id
trace_id
trajectory_id
event_id
timestamp(s)
event_type
source
plan_id
plan_version
step_id
route/capability identifier
model calls
retrieval calls
tool calls
evaluation results
interventions
replans
latency
token usage
estimated cost
final status
```

Event processing should expose at least operational telemetry for:

```text
events published/sec
events consumed/sec
consumer lag
processing latency
retry count
deduplication count
dead-letter count
replan-trigger rate
event processing failures
```

These are measurements to collect, not performance claims. No capacity or latency number should be asserted until measured.

---

# 22. Relationship to Trajectory and Execution Ledger

The Event Model and the Trajectory/Ledger Model are related but not identical.

```text
Events
= immutable observations / facts about execution

Trajectory Store
= reconstructable current + historical execution context

Execution Ledger
= append-only consequential facts for audit

ControlPlane State
= authoritative mutable state used for runtime decisions
```

A useful mental model is:

```text
Capability observation
        |
        v
      Event
        |
        +------> Event History
        |
        +------> Execution Ledger (when consequential)
        |
        +------> ControlPlane interpretation
                         |
                         v
                    State transition
                         |
                         v
                    New plan version
```

The ledger is a source of audit truth. It is not a replacement for the ControlPlane Decision Engine.

---

# 23. Relationship to Plan Versions and Replanning

Plan versions are the bridge between events and dynamic execution.

Example:

```text
Plan v1
Fast Model -> Final Verification
     |
     +--> HIGH_REASONING_UNCERTAINTY
              |
              v
       REPLAN_TRIGGERED
              |
              v
Plan v2
Reasoning Model -> Evidence Verification -> Final Verification
```

Rules:

1. Events do not mutate prior plan versions.
2. A replan creates a new plan version.
3. The triggering event records the old plan version.
4. `REPLAN_TRIGGERED` records why a new plan is needed.
5. `PLAN_UPDATED` records the new authoritative plan version.
6. New execution steps reference the new plan version.
7. Historical events retain their original linkage.

This is essential for answering:

> Why did ControlPlane choose a different execution path?

---

# 24. Infrastructure Independence

This document defines event semantics, not event infrastructure.

The architecture does not require a particular technology such as Kafka, Redis Streams, NATS, RabbitMQ, or another broker.

The implementation must preserve these semantic properties regardless of transport:

```text
structured events
stable schemas
traceability
bounded retries
idempotent consumers
persistence where required
causation/correlation
safe ordering assumptions
backpressure/failure isolation
```

Infrastructure choices belong to the scale/runtime architecture and should be selected from measured requirements rather than introduced merely to signal enterprise scale.

---

# 25. Anti-Patterns

## 25.1 Route-to-route control

```text
RAG route -> SQL route
```

**Forbidden.**

Use:

```text
RAG -> DATA_REQUIRED -> Event Bus -> ControlPlane -> Replan -> SQL
```

## 25.2 Event Bus as brain

```text
Event type -> hard-coded route selector
```

**Forbidden.**

The event bus transports facts; ControlPlane interprets them.

## 25.3 Events as hidden commands

```text
"MODEL_FAILURE": { "call_model_b_next": true }
```

**Forbidden.**

The event should report the failure. The decision engine chooses the next action.

## 25.4 Mutable historical events

**Forbidden.**

Corrections are new events with causal links to earlier facts.

## 25.5 Unbounded event/replan recursion

**Forbidden.**

All recovery paths must be bounded by retries, cost, latency, risk, policy, and execution limits.

## 25.6 Logging-only events

A state transition that can affect replanning, policy, safety, trust, or audit must be an explicit structured event, not only a log line.

---

# 26. Canonical End-to-End Examples

## Example A - Insufficient Retrieval

```text
Query
  |
  v
Plan v1: RAG -> Model -> Verify
  |
  v
RAG capability
  |
  +--> RETRIEVAL_INSUFFICIENT
          |
          v
      Event Bus
          |
          v
      ControlPlane
          |
          +--> inspect evidence + risk + budget
          |
          +--> REPLAN_TRIGGERED
          |
          +--> PLAN_UPDATED (v2)
          |
          v
      Alternate Retrieval
          |
          v
      Verify
```

## Example B - High Action Risk

```text
Agent proposes external action
          |
          v
      HIGH_ACTION_RISK
          |
          v
       Event Bus
          |
          v
      ControlPlane
          |
          +--> policy evaluation
          +--> permission evaluation
          +--> human requirement
          |
          v
  HUMAN_REVIEW_REQUIRED
          |
          v
  Human approves / rejects
          |
          v
  New authorized execution step
```

## Example C - Model Disagreement

```text
Model A ----\
             > MODEL_DISAGREEMENT
Model B ----/          |
                       v
                   ControlPlane
                       |
             +---------+---------+
             |                   |
        add verifier        stronger model
             |                   |
             +---------+---------+
                       |
                       v
                   Verify result
```

The `MODEL_DISAGREEMENT` event does not itself select the verifier or stronger model.

---

# 27. Implementation Contract Summary

Any runtime component implementing this model must satisfy the following invariants:

1. **Facts are events; decisions are ControlPlane responsibilities.**
2. **Routes/capabilities must not directly control one another.**
3. **Every meaningful event carries traceable execution context.**
4. **Every replan is attributable to one or more events.**
5. **Every plan change creates a new plan version.**
6. **Historical events remain immutable.**
7. **Consumers must tolerate duplicate delivery.**
8. **Ordering must not be inferred from transport arrival alone.**
9. **Security-sensitive and consequential events must remain auditable.**
10. **Event semantics remain independent of broker/queue technology.**
11. **Critical-path events may block continuation until ControlPlane decides.**
12. **Asynchronous consumers must not unnecessarily block the user path.**
13. **Retries and recovery loops are bounded.**
14. **Observability must connect events to trajectory, plan, evidence, cost, latency, intervention, and final outcome.**
15. **New event types require a distinct semantic need and a versioned contract.**

---

# Event Contract Checklist

- [ ] Every event has a stable `event_id`
- [ ] `event_type` is from the canonical taxonomy or an explicitly approved extension
- [ ] `event_version` is present
- [ ] `request_id` is present
- [ ] `trace_id` is present
- [ ] `trajectory_id` is present for active execution events
- [ ] `plan_id` / `plan_version` are present when the event belongs to a planned execution
- [ ] `step_id` is present when a specific execution-graph step is known
- [ ] `source` identifies the semantic producer
- [ ] `severity` is assigned contextually
- [ ] `confidence` is included when the assertion is inferential or evaluative
- [ ] Evidence references are attached for important findings
- [ ] `occurred_at` and `published_at` are recorded
- [ ] `correlation_id` is used for related event groups where needed
- [ ] `causation_id` is used when one event directly caused another
- [ ] Ordering assumptions are not based on transport arrival order
- [ ] Consumers are idempotent against duplicate events
- [ ] Deduplication is implemented for state-changing reactions
- [ ] Retry behavior is bounded
- [ ] Failure/dead-letter behavior is observable
- [ ] Security-sensitive events are persisted and access-controlled appropriately
- [ ] Events required for audit/replanning are reconstructable from persistent history
- [ ] Event semantics are independent of Kafka/Redis/NATS/RabbitMQ or other infrastructure
- [ ] Routes publish facts instead of directly invoking other routes
- [ ] Only ControlPlane interprets events into interventions/replanning decisions
- [ ] `REPLAN_TRIGGERED` records the causal reason for replanning
- [ ] `PLAN_UPDATED` records the resulting plan version
- [ ] No event is used as a hidden command
- [ ] No historical event is silently mutated
- [ ] Cost and latency implications are observable
- [ ] Human-review and human-override events are auditable
- [ ] Event schema changes preserve backward compatibility or explicitly version the contract
