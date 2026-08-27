# ControlPlane.ai — Trajectory Store + Execution Ledger

**Document:** `docs/ARCHITECTURE/TRAJECTORY_AND_LEDGER.md`  
**Status:** PLANNED — architecture/contract specification; not an implementation claim  
**Scope:** Competition Prototype / R2, with production evolution boundaries explicitly identified  
**Subsystem:** State + Governance + Observability  

---

## 0. Architectural Position

ControlPlane does not govern only the final response. For multi-step, tool-using, stateful, agentic, or multi-agent execution, the governed object is the **complete execution trajectory**.

The trajectory is the evolving record of what the system attempted, what it accessed, what it was allowed to do, what actually happened, what evidence appeared, how risk changed, how ControlPlane intervened, and how the workflow ended.

This document defines two complementary records:

```text
Trajectory Store
= reconstructable execution state + workflow history

Execution Ledger
= append-only record of consequential execution facts
```

They are related, but they are not interchangeable.

The Trajectory Store exists primarily to support runtime state recovery, inspection, replay/reconstruction, replanning, and operational visibility.

The Execution Ledger exists primarily to establish a durable, attributable sequence of consequential facts for governance, risk analysis, permission lineage, audit history, and post-execution investigation.

Neither subsystem becomes the ControlPlane's decision engine. ControlPlane remains the authority for planning, authorization, risk decisions, intervention, replanning, trust, and human escalation. MCP remains a capability/interoperability fabric rather than the system's brain.

---

## 1. Purpose

The purpose of the Trajectory Store + Execution Ledger subsystem is to provide a common architectural contract for understanding and governing execution across the full lifecycle:

```text
request
  ↓
understand
  ↓
plan
  ↓
execute
  ↓
observe
  ↓
evaluate
  ↓
decide
  ↓
intervene / replan
  ↓
verify
  ↓
respond / act
  ↓
learn
```

The subsystem must make it possible to answer, for a single execution:

```text
What was requested?
What did ControlPlane initially understand?
What plan was selected?
What plan versions existed?
Which route/node executed?
Which models were invoked?
What data or documents were accessed?
Under which permissions?
Which tools were proposed, authorized, denied, modified, or executed?
What actions occurred?
What intermediate state changed?
Which events were emitted?
What risk signals appeared?
What evaluations were produced?
Why did ControlPlane intervene?
What human approvals or overrides occurred?
What partial execution occurred before failure or termination?
What external destinations were reached?
What was the final outcome?
Did the intervention improve the trajectory?
```

The subsystem therefore acts as the state and evidence backbone for trajectory-level governance rather than as a conventional application log.

---

## 2. Why Trajectory-Level Governance Is Needed

A final-response-only model is insufficient for agentic and multi-step execution.

An individual step may be acceptable in isolation while the sequence becomes unsafe or policy-inconsistent when composed with prior steps. Relevant examples include:

- cumulative data exposure across multiple retrievals
- cumulative permissions acquired through different capabilities
- repeated or escalating tool use
- an initially harmless read followed by a consequential write
- multiple agents combining individually valid outputs into an invalid action
- a model using another agent as an indirect path to restricted data
- partial execution in which an action occurs before a later control blocks the workflow
- a replan that materially changes the expected path
- a final answer that appears safe even though the execution touched inappropriate resources

The research basis used for the current architecture explicitly frames agentic risk as a property of **trajectory, state, lineage, permissions, and cumulative actions**, rather than only of an individual message or final response. fileciteturn2file1L255-L258

The architecture therefore treats trajectory state as a first-class control object. The current agent operating rules explicitly require trajectory state, permission/data lineage, persistent execution state, and an append-only ledger for consequential facts. fileciteturn3file1L240-L284 fileciteturn2file5L810-L914

### Core principle

> **Risk is a function of what has happened across the execution, not merely what the last model said.**

A runtime decision for an agentic workflow should therefore consider, where applicable:

```text
current step
+
prior trajectory state
+
cumulative permissions
+
cumulative data exposure
+
cumulative action impact
+
new evidence
+
current policy
```

A final-response check is not a substitute for trajectory governance.

---

## 3. Scope

This document covers the conceptual architecture and contracts for:

1. trajectory representation
2. execution history
3. execution ledger records
4. identifier and correlation strategy
5. event linkage
6. plan and route linkage
7. model, retrieval, data, permission, tool, action, evaluation, and intervention records
8. partial execution
9. human approval and override history
10. final outcomes
11. trust/evaluation linkage
12. immutability boundaries
13. privacy and sensitive-data handling
14. retention and reconstruction principles
15. dashboard and analytics requirements
16. failure behavior
17. prototype versus future production scope
18. implementation-facing interfaces

This document does **not** define:

- a concrete database technology
- a concrete event broker
- a cryptographic compliance product
- a universal enterprise audit platform
- a full authorization engine
- a full workflow scheduler
- a private model-internals inspection mechanism
- a final production retention policy for every jurisdiction
- private model chain-of-thought storage

The architecture remains implementation-agnostic unless an existing project contract has already established a specific technology.

---

## 4. Design Principles

### 4.1 Trajectory is first-class

For non-trivial execution, the trajectory is a governed object rather than a side-effect of logging.

### 4.2 ControlPlane remains authoritative

The store and ledger record state and facts. They do not independently decide whether execution is allowed to continue.

### 4.3 MCP is not the brain

MCP or another capability fabric may expose tools, models, data, retrieval, and enterprise systems, but the governance record must remain owned by the ControlPlane domain.

### 4.4 State and audit history are distinct

Mutable operational state is useful for runtime recovery. Append-only consequential facts are required for durable governance history. They must not be collapsed into one undifferentiated record.

### 4.5 Structured rationale, not private reasoning

Store structured decision rationale, evidence references, policy context, confidence, and decision outcomes. Do **not** store private model chain-of-thought.

### 4.6 No silent historical mutation

Historical consequential facts must not be rewritten to make the execution look cleaner after the fact. Corrections are represented as new records or explicit superseding metadata.

### 4.7 Event-driven linkage

Events are the normalized mechanism for connecting capability execution, state change, evaluation, intervention, and replanning without direct route-to-route coupling.

### 4.8 Boundedness

Trajectory capture must respect cost, latency, retention, privacy, and execution budgets. The system must not become the bottleneck it is designed to control.

### 4.9 Prototype simplicity

The R2 prototype needs production-compatible interfaces, not production-level infrastructure complexity. Current scale guidance explicitly discourages infrastructure added merely for appearance. fileciteturn2file10L1859-L1886

---

# 5. Trajectory Definition

## 5.1 Conceptual definition

A **trajectory** is the ordered and causally linked representation of an AI execution from request initiation through final outcome, including significant state changes and governance decisions that occur along the way.

Conceptually:

```text
Trajectory
│
├── Request context
├── Query / task
├── Context
├── Query profile
├── Policy context
├── Risk / confidence state
├── Initial plan
├── Plan versions
├── Execution graph changes
├── Route / node executions
├── Model invocations
├── Retrieval operations
├── Data/document access
├── Permission lineage
├── Tool/action proposals
├── Authorization decisions
├── Tool/action execution
├── Intermediate state changes
├── Events
├── Evaluations
├── Risk signals
├── Interventions
├── Human approvals / overrides
├── Partial execution states
├── External destinations
├── Verification
└── Final outcome
```

The architecture already identifies the trajectory as including query, context, data accessed, permissions, models, retrieval, tools, actions, intermediate state, evaluations, interventions, and final outcome. fileciteturn0file1L12-L46

## 5.2 What is the trajectory's unit of governance?

The trajectory is the smallest practical object on which cumulative execution risk can be reasoned about.

A single request can contain:

- multiple routes
- multiple plan versions
- multiple model calls
- multiple retrievals
- multiple tools
- multiple agents
- multiple permission contexts
- multiple human checkpoints
- multiple interventions
- partial execution before termination

The trajectory binds those pieces into one governance context.

## 5.3 Trajectory states

A trajectory may conceptually move through states such as:

```text
CREATED
PLANNED
RUNNING
WAITING
PAUSED
REPLANNING
AWAITING_HUMAN
DEGRADED
PARTIALLY_EXECUTED
COMPLETED
ABSTAINED
BLOCKED
ABORTED
FAILED
```

The exact runtime state machine is defined elsewhere. This document only requires that the trajectory record can represent the transition history and current state.

---

# 6. What Belongs in the Trajectory Store

The Trajectory Store is the **reconstructable execution history and operational state** of the workflow.

It should contain enough information to reconstruct the evolving workflow without requiring private model internals.

## 6.1 Core trajectory header

Conceptual fields:

```text
trajectory_id
request_id
trace_id
conversation_id / session_id
application_id
principal / actor reference
created_at
updated_at
status
policy_context
current_plan_id
current_plan_version
current_node_id
current_risk_state
current_confidence_state
current_trust_state
```

## 6.2 Request and context

Store, subject to privacy policy:

```text
query/task representation
relevant request context
query fingerprint
application context
user/session context reference
initial policy context
initial constraints
initial budgets
```

The store should not indiscriminately duplicate every piece of request metadata if the source system already provides a stable reference.

## 6.3 Execution path

The store must support:

```text
node creation
node start
node completion
node failure
node retry
node skip
node replacement
node insertion
node deletion
node rerouting
parallel branches
join/synchronization
pause
resume
human wait
termination
```

These capabilities are aligned with the mutable execution graph defined by the architecture. fileciteturn1file3L705-L748

## 6.4 Evidence and state

The trajectory should track references to:

```text
evidence collected
evidence accepted/rejected
evidence conflicts
current risk state
confidence state
verification state
important intermediate state changes
```

The trajectory may reference large payloads or external artifacts rather than duplicating them.

## 6.5 Governance history

The store should be able to reconstruct:

```text
policy decisions
risk decisions
authorization outcomes
interventions
replans
human review states
final trust result
final status
```

## 6.6 Operational metadata

At minimum, where available:

```text
latency
cost estimate
token usage
retry count
replan count
time spent waiting for human approval
external call count
```

The scale architecture requires persistent execution state and traceable histories rather than state held only in process memory. fileciteturn2file9L1575-L1607

---

# 7. What Belongs in the Execution Ledger

The Execution Ledger is the **append-only record of consequential facts**.

It should capture facts that materially affect:

- governance
- permissions
- data lineage
- external actions
- policy decisions
- risk decisions
- human approvals
- interventions
- execution accountability

The existing architecture explicitly identifies data accessed, documents accessed, tools called, permissions used, models used, actions taken, external destinations, state changes, human approvals, and interventions as ledger material. fileciteturn1file3L1261-L1276

## 7.1 Ledger entry concept

A conceptual ledger entry contains:

```text
ledger_entry_id
trajectory_id
event_id
timestamp
sequence_position
actor/source
actor_type
capability / action type
resource reference
authorization context
policy version/reference
result/status
evidence/reference
risk context
correlation metadata
```

The current runtime governance guidance requires ledger attribution to trajectory, event, time, actor/source, action/capability, authorization context, policy version, result/status, and evidence/reference. fileciteturn2file5L866-L913

## 7.2 Consequential fact categories

The ledger should support at least:

```text
DATA_ACCESS
DOCUMENT_ACCESS
PERMISSION_GRANTED
PERMISSION_USED
PERMISSION_DENIED
MODEL_INVOCATION
RETRIEVAL_EXECUTION
TOOL_PROPOSAL
TOOL_AUTHORIZATION
TOOL_DENIAL
TOOL_EXECUTION
ACTION_PROPOSAL
ACTION_AUTHORIZATION
ACTION_EXECUTION
EXTERNAL_DESTINATION
POLICY_DECISION
RISK_DECISION
INTERVENTION
HUMAN_APPROVAL
HUMAN_OVERRIDE
STATE_CHANGE
VERIFICATION_RESULT
FINAL_OUTCOME
```

These are conceptual categories, not a frozen event enum.

---

# 8. Trajectory History vs Audit Ledger

These terms must remain distinct.

| Dimension | Trajectory Store | Execution Ledger |
|---|---|---|
| Primary purpose | Reconstruct and operate on workflow history/state | Preserve consequential execution facts |
| Runtime use | High | Low to medium; may be queried for governance |
| Mutability | Current state may evolve; history must remain reconstructable | Append-only |
| Supports replanning | Yes | Indirectly, as evidence/history |
| Supports recovery | Yes | No, not by itself |
| Supports operational dashboards | Yes | Yes, especially governance views |
| Audit truth for consequential facts | Supporting source | Primary historical record |
| Typical content | Steps, graph, current state, evidence references, status | Access, permission, action, authorization, intervention, outcome facts |
| Historical correction | Preserve version/history | Add explicit correction/superseding entry; do not rewrite |
| Retention pressure | Often higher due to state volume | High-value records may justify longer retention |

### Rule

> **Trajectory Store tells the story of the evolving workflow. Execution Ledger preserves the consequential facts that must not disappear from history.**

The ledger is not a replacement for the Decision Engine, and the Trajectory Store is not merely an audit log.

---

# 9. Identifier Model

The architecture already requires request and trace identifiers at the API boundary. fileciteturn0file1L247-L272

The trajectory subsystem adds a dedicated `trajectory_id`.

## 9.1 Request ID

`request_id` identifies the logical inbound request received by the ControlPlane boundary.

Use it to answer:

> Which user/application request initiated this execution?

A single request should normally map to one primary trajectory, while future contracts may allow explicitly linked sub-trajectories for long-running or delegated workflows.

## 9.2 Trace ID

`trace_id` identifies the distributed execution trace associated with the request and should remain stable across internal operations that form the same execution trace.

Use it for cross-component correlation.

## 9.3 Trajectory ID

`trajectory_id` identifies the governed execution trajectory.

It is distinct from `request_id` because the governed execution may evolve independently of the inbound API request boundary.

## 9.4 Event ID

`event_id` identifies one structured runtime event.

Every event that materially participates in execution history should link back to its trajectory and trace.

## 9.5 Node execution ID

Each concrete execution of an execution-graph node should have a distinct execution identity when retries, replacements, or repeated invocations are possible.

Conceptually:

```text
node_id
node_execution_id
attempt_number
```

A retry must not overwrite the previous attempt.

## 9.6 Decision ID

A major ControlPlane decision should have a distinct `decision_id`, especially when it causes:

```text
authorization
intervention
replan
model switch
human escalation
block
abort
```

## 9.7 Plan ID and Plan Version

`plan_id` identifies the logical plan.

`plan_version` identifies the concrete version used by the trajectory.

The initial plan is provisional; every material plan modification creates or references a new plan version. fileciteturn1file1L269-L304

---

# 10. Event Linkage

Events are the linkage mechanism between execution activity and the trajectory.

Conceptually:

```text
Capability
   ↓
Structured Event
   ↓
Event Bus
   ↓
ControlPlane
   ↓
Trajectory State Update
   ↓
Evaluation / Decision
   ↓
Intervention / Replan
```

The architecture explicitly requires structured events for meaningful state transitions and discourages direct route-to-route coupling. fileciteturn1file3L1288-L1331

## 10.1 Event minimum

Where relevant:

```text
event_id
request_id
trace_id
trajectory_id
timestamp
source
actor/capability
event_type
severity
confidence
evidence/reference
metadata
```

## 10.2 Event-to-ledger rule

Not every event must become a ledger entry.

Examples:

- a debug-level progress event may belong only to operational telemetry
- a `TOOL_AUTHORIZED` event should produce a ledger record
- a `PERMISSION_GRANTED` event should produce a ledger record
- a `MODEL_CALL_STARTED` event may belong to trajectory history and telemetry
- a high-consequence `ACTION_EXECUTED` event should belong to the ledger

The mapping should be explicit in the event contract rather than inferred ad hoc by consumers.

## 10.3 Event ordering

The system must not assume wall-clock timestamps alone provide a sufficient causal order.

For each trajectory, the architecture should support an explicit ordering mechanism conceptually represented as:

```text
sequence_position
parent_event_id / causal_reference where needed
```

The exact implementation is intentionally undecided.

---

# 11. Plan Version Linkage

Plan versions are part of the trajectory, not external metadata.

Example:

```text
Trajectory T1

Plan v1
  A → B → C

Event: HIGH_REASONING_UNCERTAINTY

Decision D1
  structured rationale:
  - confidence below policy threshold
  - remaining latency budget permits escalation
  - stronger reasoning capability available

Plan v2
  A → B → D → C
```

The trajectory must be able to answer:

```text
Which plan version was active?
Which nodes came from that version?
Why did the version change?
Which event or decision caused the change?
Which nodes already executed before the change?
Which nodes were inserted, skipped, replaced, or rerouted?
```

This preserves the distinction between **planned execution** and **actual execution**.

---

# 12. Route / Node Linkage

The trajectory must link each material execution to the execution graph.

Conceptually:

```text
plan_id
plan_version
route_id
node_id
node_execution_id
parent_node / dependency references
status
attempt
start/end timestamps
```

The architecture defines route history conceptually as:

```text
request_id
plan_version
from_node
to_node
reason
event
timestamp
```

and requires the query to be reconstructable from recorded history. fileciteturn1file5L1189-L1232

## 12.1 Node lifecycle

A node execution should be able to represent at least:

```text
PENDING
ACTIVE
COMPLETED
FAILED
SKIPPED
REPLACED
RETRIED
REPLANNED
HUMAN_WAIT
CANCELLED
```

## 12.2 Parallel branches

A trajectory must preserve branch identity when the plan executes parallel work.

Example:

```text
            ┌── SQL ───────┐
Query ──────┤               ├── Evidence Merge
            └── RAG ────────┘
```

Each branch remains independently attributable.

---

# 13. Model Invocation Records

Each meaningful model invocation should be traceable to the trajectory and the node that requested it.

## 13.1 Conceptual record

```text
model_invocation_id
trajectory_id
trace_id
node_execution_id
model_id
provider reference
model version
invocation purpose
input reference
output reference
request metadata
latency
token usage
estimated cost
status
failure metadata
verification/evaluation references
```

## 13.2 Do not store private chain-of-thought

The model invocation record must **not** store hidden chain-of-thought or private internal reasoning traces.

Instead store structured metadata such as:

```text
task type
selected capability
confidence
risk signals
policy checks
structured decision rationale
verification result
output/evidence references
```

Example structured rationale:

```text
Decision: switch to reasoning capability
Reason:
- request complexity is high
- current confidence is below policy threshold
- remaining latency budget permits escalation
- selected capability has a stronger observed profile for this task class
```

This matches the existing architecture's explicit requirement to store decision traces rather than private chain-of-thought. fileciteturn1file5L1236-L1255

## 13.3 Provider abstraction

Provider-specific fields must remain secondary to normalized ControlPlane fields. The existing architecture requires model/provider abstraction and prevents provider-specific code from leaking into the central planner. fileciteturn3file0L12-L33

---

# 14. Retrieval and Data-Access Records

Trajectory governance requires knowing not only that retrieval occurred, but what information was used in execution.

## 14.1 Retrieval record

Conceptually:

```text
retrieval_id
trajectory_id
node_execution_id
source_type
source_reference
retrieval_method
query/reference
result_count
selected references
retrieval scores / ranking metadata where appropriate
freshness metadata where available
evidence adequacy / retrieval quality reference
status
```

The current architecture's RAG contract already calls for sources, chunks, retrieval scores, source metadata, evidence adequacy, and freshness. fileciteturn2file0L141-L169

## 14.2 Data access record

For each meaningful access:

```text
data_access_id
trajectory_id
actor/agent
source/resource reference
operation
permission context
purpose/task reference
sensitivity classification where applicable
authorization result
data lineage/reference
external-destination relation if data leaves the system
```

## 14.3 Store references, not unnecessary copies

A trajectory record should not automatically duplicate entire source documents, database rows, or large tool payloads.

Prefer:

```text
stable source reference
small metadata envelope
selected evidence references
integrity/reference metadata where appropriate
```

over indiscriminate content duplication.

---

# 15. Permission Lineage

Permission lineage is a core governance function, especially for multi-agent execution.

The architecture requires tracking:

```text
who requested
who accessed
what data was accessed
which permission enabled it
where the data went
which agent initiated the action
which other agents participated
```

This exists partly to detect **permission laundering**, where one agent indirectly obtains or exports information another agent could not access itself. fileciteturn2file0L226-L240

## 15.1 Permission lineage model

Conceptually:

```text
Principal / User
   ↓
Application / Session
   ↓
Agent / Capability
   ↓
Permission Context
   ↓
Resource Access
   ↓
Data Use / Transformation
   ↓
Destination / Action
```

The ledger should preserve the critical edges of this chain.

## 15.2 Cumulative permissions

A trajectory-level policy decision must be able to reason over accumulated permissions rather than only the latest grant.

Example:

```text
Agent A: no access to restricted customer data
Agent B: allowed to access customer data
Agent A → asks Agent B for data
Agent B → returns restricted data
Agent A → sends result externally
```

No single isolated step necessarily explains the violation. The trajectory/ledger does.

## 15.3 Permission contract boundary

The ledger records authorization facts. It does not itself grant permissions.

Authorization remains the responsibility of the ControlPlane policy/authorization path.

---

# 16. Tool and Action Records

Tool use must be represented as a sequence of governance-relevant stages.

```text
Proposed
   ↓
Policy evaluation
   ↓
Risk evaluation
   ↓
ALLOW / MODIFY / HUMAN / BLOCK
   ↓
Execution
   ↓
Result
   ↓
Post-action verification
```

The current architecture explicitly requires ControlPlane authorization before an MCP/tool invocation and records the result into the ledger. fileciteturn2file0L196-L222

## 16.1 Tool proposal record

```text
tool_call_id
trajectory_id
node_execution_id
actor/agent
tool identifier
purpose
normalized arguments reference
risk context
permission context
proposal timestamp
```

## 16.2 Tool authorization record

```text
authorization decision
decision_id
policy reference
risk/confidence context
constraints applied
human requirement if any
```

## 16.3 Tool execution record

```text
execution status
start/end time
result reference
failure category
external side effect indicator
post-action verification reference
```

## 16.4 Tool arguments

Tool arguments may be stored where needed for governance, reproducibility, or incident reconstruction, but they must be subject to privacy and minimization rules.

For sensitive arguments, the record should prefer:

```text
redacted representation
structured summary
stable payload reference
field-level sensitivity metadata
```

rather than indiscriminate raw storage.

---

# 17. Human Approval Records

Human approval is itself a governed execution event.

A human checkpoint should be attributable to:

```text
approval_request_id
trajectory_id
decision_id
requested_at
reviewer reference
approval scope
information presented to reviewer
decision
constraints / modifications
approved action scope
approved expiry or execution boundary where relevant
review timestamp
```

The system must distinguish:

```text
human approved
human rejected
human modified
human overrode policy recommendation
human timeout
human unavailable
```

A human override must never erase the automated decision that preceded it.

---

# 18. Intervention Records

An intervention is a ControlPlane decision that changes or constrains execution.

Possible intervention classes are already established conceptually in the architecture, including:

```text
RETRY
REGENERATE
REROUTE
RETRIEVE
CHANGE_RETRIEVAL
CHANGE_MODEL
INCREASE_REASONING
DECREASE_REASONING
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

The current runtime guidance also allows decisions such as `CONTINUE`, `MONITOR`, `MODIFY`, `RETRIEVE`, `VERIFY`, `REPLAN`, `ESCALATE`, `HUMAN_REVIEW`, `BLOCK`, and `ABORT`. fileciteturn3file1L166-L181

## 18.1 Conceptual intervention record

```text
intervention_id
trajectory_id
event_id
decision_id
intervention_type
trigger
structured rationale
evidence references
policy reference
pre-intervention state
requested change
post-intervention state
outcome
```

## 18.2 Intervention linkage rule

Every material intervention should link to:

```text
what triggered it
why it was selected
what changed
whether execution continued
whether a new plan version resulted
whether the intervention helped
```

---

# 19. Risk and Confidence Linkage

Trajectory governance requires risk and confidence to evolve with execution.

The architecture explicitly maintains risk/confidence state in shared execution state. fileciteturn1file1L357-L399

## 19.1 Risk state is not a single immutable score

The record should support a structured risk vector, potentially including:

```text
factuality
hallucination
reasoning
privacy
PII
security
bias
compliance
financial
action
reputational
```

The product thesis already frames these as distinct dimensions rather than reducing risk to a single opaque category. fileciteturn0file3L397-L445

## 19.2 Trajectory-level risk accumulation

The store/ledger should allow future risk logic to inspect cumulative signals such as:

```text
number of tool calls
sensitivity of accessed data
permission expansion
external destination count
high-impact action attempts
model disagreement
retrieval insufficiency
evidence conflicts
replan frequency
behavioral drift
```

The architecture identifies Behavioral Drift Score as a research-derived trajectory signal comparing expected versus actual trajectory behavior. fileciteturn1file3L1335-L1351

The score itself is outside this document's implementation contract; the trajectory records must simply preserve the inputs needed by the relevant future evaluator.

---

# 20. Evaluation and Trust Linkage

Every evaluation relevant to runtime governance should link to the trajectory and the execution object it evaluates.

Conceptually:

```text
evaluation_id
trajectory_id
node_execution_id / artifact reference
evaluator type
input reference
score(s)
confidence
issues
 evidence references
recommended action
policy threshold / context
result
```

The architecture requires modular evaluators to return structured results such as score, confidence, issues, evidence, and recommended action. 

## 20.1 Evaluation targets

Possible targets include:

```text
query profile
retrieval quality
model output
evidence grounding
reasoning quality
safety
privacy
PII
bias
security
action risk
cost
latency
consistency
final response
external action
```

## 20.2 Trust report linkage

The final trust report should reference the relevant trajectory/evaluation records rather than creating an isolated trust artifact disconnected from execution history.

---

# 21. Intermediate State and State Changes

The Trajectory Store should capture **meaningful intermediate state** that affects governance, recovery, replanning, or reconstruction.

Examples:

```text
current plan
current node
completed/pending nodes
risk state
confidence state
evidence set
retrieval adequacy
authorization state
pending human approval
budget consumption
external action state
```

Not every local variable or transient implementation object belongs in the trajectory.

The rule is:

> Store state that changes what ControlPlane believes, permits, plans, verifies, or can explain.

---

# 22. Partial Execution States

Partial execution is a first-class case, not an exception to be hidden.

Example:

```text
READ customer record
   ✓ completed

PREPARE external email
   ✓ completed

SEND email
   ✗ blocked by policy
```

The trajectory must show:

```text
what happened before the block
what was merely proposed
what was authorized
what was actually executed
what did not execute
what external side effect, if any, already occurred
what state remains
what recovery/intervention followed
```

## 22.1 No false rollback assumption

The system must not assume that blocking a later step reverses earlier external effects.

If a previous action had already occurred, the ledger retains that fact.

## 22.2 Partial completion status

The final trajectory outcome may therefore be:

```text
COMPLETED
COMPLETED_WITH_LIMITATIONS
PARTIALLY_EXECUTED
ABSTAINED
BLOCKED
ABORTED
FAILED
```

The exact enum can be established by the broader runtime contract later.

## 22.3 Recovery implication

The Trajectory Store should allow the ControlPlane to resume or replan from a known partial state where that behavior is supported.

---

# 23. External Destinations

External destinations are a governance-critical concept.

For any operation that can cause data or effects to leave the ControlPlane-managed environment, the trajectory/ledger should support:

```text
destination reference
destination type
actor/agent
what was sent or changed
why it was sent
authorization context
policy decision
result
verification status
```

Where exact payload storage is inappropriate, use a secure reference plus structured summary and sensitivity metadata.

Examples include:

```text
email recipient
external API
CRM system
cloud storage location
third-party service
customer-visible interface
financial system
```

The architecture explicitly lists external destinations as part of the ledger/governed execution state. fileciteturn2file0L226-L240

---

# 24. Final Outcome

The trajectory must terminate in a state that is linked to all relevant execution evidence.

Conceptual final outcome:

```text
final_status
final_response reference
final_action reference
final_verification status
trust_report reference
limitations
risk summary
interventions summary
human approvals summary
cost
latency
```

The final outcome must not erase intermediate execution facts.

A response that looks successful while containing a blocked or partially executed action must remain represented as such.

---

# 25. Immutability and Append-Only Requirements

## 25.1 Execution Ledger

The ledger is append-only for audit purposes.

Historical consequential facts must not be silently mutated.

This matches the current project guidance that ledger records are append-only and should not be silently rewritten. fileciteturn2file5L897-L913

## 25.2 Trajectory Store

The Trajectory Store may contain mutable current state, but history must remain reconstructable.

For example:

```text
current_plan_version = 3
```

may change from version 2 to version 3 in operational state, while the history still preserves:

```text
Plan v2 existed
Plan v3 existed
Event E17 triggered transition
Decision D8 caused replan
```

## 25.3 Corrections

When a historical fact is found to be incorrect:

```text
Do not overwrite the original fact.

Append:
CORRECTION / SUPERSEDING_RECORD
```

with a reference to the original record.

The exact correction mechanism is a future implementation decision.

## 25.4 Tamper evidence

Cryptographic tamper-evidence, signed audit exports, WORM storage, and independent compliance vaults are **future production capabilities**, not prototype requirements unless already mandated elsewhere.

Do not claim the prototype is an insurance-grade audit platform merely because it has append-only logical semantics.

---

# 26. Privacy and Sensitive-Data Considerations

Trajectory governance creates a tension:

```text
Need enough information to explain what happened
                    vs.
Need to minimize sensitive data retention
```

The architecture must therefore prefer **reference + metadata** over indiscriminate payload duplication.

## 26.1 Sensitive categories

Potentially sensitive trajectory content includes:

```text
user identifiers
session identifiers
PII
financial information
enterprise confidential data
credentials/secrets
tool arguments
query text
documents/chunks
database results
external recipient information
human reviewer identity
```

## 26.2 Never store secrets as ordinary trajectory data

Do not store:

```text
API keys
passwords
access tokens
private keys
session cookies
credential material
```

in trajectory or ledger records.

Store secure references to the authorization context where necessary.

## 26.3 Data minimization

The implementation should support:

```text
redaction
field-level minimization
reference-based storage
sensitivity labels
payload suppression
access-controlled inspection
```

## 26.4 Query and output storage

Prototype behavior may retain enough request/output content to demonstrate trajectory reconstruction, but production policy must define:

```text
what is retained
who can view it
how long it is retained
what is redacted
how deletion requests interact with governance records
```

## 26.5 Privacy versus audit tension

A governance record is not automatically entitled to store all original content forever.

The design should distinguish:

```text
fact of access
identity/context of access
resource reference
sensitivity metadata

from

full raw payload
```

---

# 27. Retention Considerations

Retention is a policy domain, not a hard-coded property of the store.

## 27.1 Prototype

Prototype retention should be sufficient for:

- debugging
- demo reconstruction
- evaluator analysis
- dashboard history
- learning experiments
- failure analysis

Exact durations should be configurable rather than embedded in architecture prose.

## 27.2 Future production

Production retention may need differentiated policies for:

```text
operational trajectory state
execution ledger facts
raw payload references
sensitive content
human approval records
evaluation results
aggregated analytics
```

Different data classes may have different legal, operational, and privacy requirements.

## 27.3 Deletion semantics

Future production must explicitly determine what happens when underlying content is deleted while governance metadata must still remain explainable.

Possible design direction:

```text
retain audit fact
remove raw payload
retain stable reference / tombstone
retain sensitivity metadata
```

This is an open design area, not a prototype commitment.

---

# 28. Replay and Reconstruction Requirements

Replay must be defined carefully because **replay is not the same as re-execution**.

## 28.1 Reconstruction

At minimum, the system should be able to reconstruct:

```text
request
initial profile
plan versions
route/node sequence
events
model/tool/retrieval invocations
risk/evaluation changes
interventions
human decisions
partial execution
final outcome
```

## 28.2 Deterministic replay

A future production system may need deterministic or semi-deterministic replay for selected workflows.

This would require preserving additional information such as:

```text
plan versions
configuration versions
policy version
model/provider version
retrieval state/reference
tool versions
input/output references
randomness controls where relevant
external-state snapshots where feasible
```

The prototype should not promise deterministic full-world replay.

## 28.3 Safe reconstruction mode

Dashboard inspection should support a **read-only reconstruction mode** that does not re-execute tools or external actions.

This is critical for incident analysis.

## 28.4 Replay boundaries

A replay system must clearly distinguish:

```text
RECONSTRUCT HISTORY
vs.
SIMULATE DECISION PATH
vs.
RE-EXECUTE WORKFLOW
```

These are materially different operations.

---

# 29. Dashboard Requirements

The trajectory subsystem must make the dashboard capable of answering the architecture's core operational questions:

```text
What happened?
Why?
Which route was used?
What failed?
What triggered intervention?
What changed?
Did the intervention help?
What did it cost?
```

The current architecture defines a request timeline from query through plan, execution graph, events, replans, evaluations, interventions, final answer, and trust report. fileciteturn1file5L1259-L1353

## 29.1 Request / trajectory explorer

Show:

```text
trajectory identifier
request/trace identifiers
status
current/final plan version
current/final route
risk summary
trust summary
cost
latency
```

## 29.2 Timeline

Visualize:

```text
Query
 ↓
Profile
 ↓
Plan v1
 ↓
Retrieval
 ↓
Model A
 ↓
Risk event
 ↓
Replan → Plan v2
 ↓
Model B
 ↓
Verifier
 ↓
Human approval
 ↓
Action
 ↓
Final outcome
```

## 29.3 Execution graph

Node states should make visible:

```text
pending
active
completed
failed
skipped
replanned
human_wait
```

## 29.4 Decision inspector

For every major decision:

```text
decision
trigger
structured rationale
evidence/signals
confidence
policy
alternative considered where available
action taken
outcome
```

Do not show hidden chain-of-thought.

## 29.5 Permission/data lineage view

Show:

```text
principal
agent
permission
resource
access
transformation/use
destination
```

This is particularly important for multi-agent workflows.

## 29.6 Partial execution view

Make it immediately visible whether:

```text
nothing executed
some steps executed
external effects occurred
later steps were blocked
human approval was pending
workflow was aborted
```

---

# 30. Learning and Analytics Usage

Every meaningful completed trajectory can contribute structured data to the learning loop.

The architecture explicitly expects completed executions to contribute query, profile, plan, trajectory, events, risk, interventions, outcome, feedback, cost, latency, and trust signals for future improvement. fileciteturn3file0L74-L106

## 30.1 Potential analytics

Trajectory data can support:

```text
route effectiveness
model capability profiles
retrieval quality analysis
intervention success rate
replanning frequency
risk false-positive / false-negative analysis
human escalation rate
human override rate
cost by trajectory class
latency by trajectory class
failure clustering
permission misuse patterns
behavioral drift patterns
```

## 30.2 Learning inputs

Future learning systems may learn:

```text
query profiling
model routing
risk scoring
intervention selection
verifier selection
```

The initial prototype does not need sophisticated online learning. It should preserve the data required to support future research without making online training a critical-path dependency.

## 30.3 Analytics must be asynchronous where possible

Dashboard aggregation, long-term analytics, offline evaluation, benchmarking, trend detection, and learning signals should remain off the user-critical path wherever possible. The scale guide explicitly separates critical execution from asynchronous observability/analytics. fileciteturn0file4L270-L313

---

# 31. Failure Cases

The subsystem must handle failure as part of trajectory state rather than as missing data.

## 31.1 Store unavailable during execution

Required conceptual behavior:

```text
Do not block low-risk execution indefinitely solely for analytics persistence.
Preserve critical governance state through the runtime's agreed mechanism.
Record persistence degradation.
Do not falsely mark the trajectory fully audited if required records were lost.
```

The exact fallback architecture is an open implementation concern.

## 31.2 Duplicate event

The system should tolerate duplicate delivery where the event architecture permits at-least-once behavior.

Ledger insertion should conceptually support idempotent handling without changing historical truth.

## 31.3 Out-of-order event

The trajectory should preserve event receipt and causal ordering metadata sufficiently to reconstruct the execution.

## 31.4 Partial write

A partially persisted trajectory must be recognizable as incomplete rather than silently presented as complete.

## 31.5 Tool executes but result is lost

The ledger should distinguish:

```text
action execution occurred
result was not observed
verification is unknown
```

from:

```text
action did not execute
```

## 31.6 Human approval timeout

Represent:

```text
approval requested
approval pending
approval timed out
workflow paused / aborted / degraded
```

not simply `HUMAN_REVIEW_FAILED`.

## 31.7 Policy decision unavailable

A consequential action must not silently proceed because the ledger could not record the authorization context.

The broader policy engine defines whether the safe fallback is block, human escalation, or a degraded path.

## 31.8 Storage/retention conflict

A future production system may need to retain the governance fact while deleting raw sensitive payloads. The record model therefore must permit references and tombstones.

---

# 32. What Should NOT Be Stored

The Trajectory Store and Execution Ledger are not universal dumping grounds.

Do **not** store the following by default:

## 32.1 Private model chain-of-thought

Never store hidden model reasoning traces.

Store structured rationale and execution metadata instead.

## 32.2 Secrets

Never store:

```text
API keys
passwords
authentication tokens
private keys
session secrets
```

## 32.3 Unbounded raw payloads

Do not copy every:

```text
full document
entire database result
entire chat history
large model context
large tool response
```

into every trajectory record.

Use references, selected evidence, summaries, and metadata where sufficient.

## 32.4 Low-value debug noise

Avoid turning the ledger into a generic logging sink.

Routine debug information belongs in ordinary telemetry when it is not a consequential execution fact.

## 32.5 Duplicate canonical data

Do not replicate authoritative policy, model, capability, or identity registries in full inside every trajectory.

Store stable references plus the version/context needed to reconstruct the decision.

## 32.6 Unsupported speculative metadata

Do not add fields merely because they might be useful someday. Every trajectory/ledger field should have a runtime, governance, reconstruction, dashboard, or learning purpose.

---

# 33. Prototype Scope vs Future Production Scope

## 33.1 Prototype — required

The prototype should provide a clean, implementation-agnostic contract for:

```text
trajectory_id
request_id
trace_id
plan_id / plan_version
route/node linkage
structured events
model invocation metadata
retrieval metadata
basic data/document access references
permission context/reference
tool proposal/authorization/execution records
intervention records
human approval records
risk/evaluation linkage
partial execution states
final outcome
append-only logical ledger semantics
basic reconstruction
basic dashboard timeline
```

The prototype should prioritize observability, state persistence, clear interfaces, and measured behavior at the stated competition scale rather than enterprise infrastructure complexity. fileciteturn2file4L614-L650

## 33.2 Prototype — explicitly not required

Do not require:

```text
multi-region immutable archival
cryptographic notarization
formal WORM compliance storage
enterprise legal hold orchestration
cross-jurisdiction retention automation
full deterministic world replay
universal identity federation
enterprise-grade SIEM integration
massive distributed event infrastructure
full data-loss-prevention platform
```

## 33.3 Future production scope

Potential future extensions include:

```text
cryptographic integrity / tamper evidence
signed ledger exports
policy-aware retention classes
secure audit vaults
fine-grained audit access controls
field-level encryption
privacy-preserving analytics
cross-agent lineage graphs
cross-application trajectory correlation
long-lived durable workflow recovery
deterministic replay for selected workloads
external-state snapshots
regional data residency controls
compliance export formats
legal hold / retention workflows
high-volume event ingestion and archival
```

These are future capabilities, not commitments for the R2 prototype.

---

# 34. Multi-Agent Governance

The ledger is especially important when several agents or capabilities participate in one trajectory.

## 34.1 Shared trajectory

All participating agents should map their meaningful actions into the same governed trajectory or an explicitly linked child trajectory.

Conceptually:

```text
Trajectory T1
│
├── Agent A
│    ├── retrieval
│    └── proposal
│
├── Agent B
│    ├── data access
│    └── tool call
│
└── ControlPlane
     ├── authorization
     ├── risk
     ├── intervention
     └── final decision
```

## 34.2 Agent identity

Each agent contribution should be attributable by:

```text
agent_id / capability reference
parent agent where applicable
application/session context
permission context
node/step reference
```

## 34.3 Permission laundering defense

The trajectory must allow the policy layer to determine that:

```text
Agent A requested data
Agent B accessed data
Agent B returned the data
Agent A forwarded the data externally
```

even when the individual calls appear valid in isolation.

## 34.4 Cumulative action risk

The ControlPlane must be able to compute governance signals from the composition of actions rather than checking only the most recent tool call.

This is one of the main architectural reasons the ledger is a first-class subsystem.

---

# 35. Relationship to Existing ControlPlane Layers

The Trajectory Store + Execution Ledger sits inside the existing architecture as a shared state/governance subsystem.

```text
                CONTROLPLANE CORE
                       │
        ┌──────────────┼───────────────┐
        │              │               │
   Intelligence      State           Policy
        │              │               │
        │       Trajectory Store       │
        │       Execution Ledger      │
        │       Event History         │
        │              │               │
        └──────────────┼───────────────┘
                       │
                 Decision / Replan
                       │
                MCP Capability Fabric
                       │
          Models / Data / Retrieval / Tools
                       │
                 Evaluations
                       │
                 Interventions
                       │
              Final / Human Outcome
```

This is consistent with the established architecture, which identifies Trajectory Store and Execution Ledger as first-class state components alongside execution state and event history. fileciteturn0file1L146-L189

---

# 36. Runtime Interaction Contract

Conceptually, execution should follow:

```text
1. Request created
   ↓
2. request_id / trace_id assigned
   ↓
3. trajectory_id created
   ↓
4. Initial query/profile/policy context recorded
   ↓
5. Initial plan + plan_version recorded
   ↓
6. Node/route starts
   ↓
7. Model/retrieval/tool capabilities execute
   ↓
8. Events update trajectory state
   ↓
9. Consequential events append ledger facts
   ↓
10. Evaluators add structured trust/risk signals
   ↓
11. ControlPlane decides CONTINUE / MODIFY / REPLAN / etc.
   ↓
12. New plan version or node transition recorded where applicable
   ↓
13. Human approval / intervention recorded when applicable
   ↓
14. External action + post-action verification recorded
   ↓
15. Final outcome recorded
   ↓
16. Async analytics / learning consumes trajectory history
```

The store and ledger do not independently advance the workflow. They record and expose execution facts for the ControlPlane's runtime decisions.

---

# 37. Performance and Scale Considerations

The architecture assumes approximately 10,000 user interactions per week and recognizes that each interaction may create many internal events. The scale guide treats tens of thousands to 100,000+ internal events per week as a plausible planning range before agentic amplification, not as a measured capacity claim. fileciteturn1file0L86-L144

## 37.1 Critical path

Only the minimum required state writes should block the user-critical path.

Possible critical writes include:

```text
trajectory initialization
critical authorization fact
critical action fact
required state checkpoint
final outcome
```

## 37.2 Asynchronous writes

Possible asynchronous work:

```text
analytics aggregation
historical indexing
long-term learning datasets
dashboard materialization
offline evaluation
trend analysis
```

## 37.3 Storage pressure

Large payloads should use references when practical.

The trajectory record should favor:

```text
small structured metadata
stable references
version identifiers
selective evidence
```

over unbounded payload duplication.

## 37.4 Failure isolation

A failure in analytics should not automatically fail user execution.

A failure in required governance state for a consequential action is different and must be treated according to the action's policy/risk class.

---

# 38. Security Boundaries

## 38.1 Access to trajectory history

Trajectory history may contain sensitive information and should itself be treated as protected data.

Access should be policy-controlled by role/use case.

## 38.2 Separation of operational and governance access

An operator may be allowed to inspect:

```text
status
risk summary
route
latency
cost
interventions
```

without being allowed to inspect:

```text
raw sensitive document contents
private user context
full tool payloads
restricted source data
```

## 38.3 No authority escalation through the ledger

Writing an entry to the ledger must never imply authorization to perform the corresponding action.

## 38.4 No direct capability bypass

Capabilities should not be able to execute consequential actions while bypassing ControlPlane authorization. The current operating rules explicitly prohibit direct capability-to-capability bypasses that skip required intervention points. fileciteturn3file1L166-L181

---

# 39. Failure Taxonomy Alignment

Trajectory and ledger records should align with the existing failure taxonomy:

```text
QUERY_FAILURE
DATA_FAILURE
RETRIEVAL_FAILURE
MODEL_FAILURE
REASONING_FAILURE
EVIDENCE_FAILURE
POLICY_FAILURE
TOOL_FAILURE
RESOURCE_FAILURE
```

The architecture explicitly requires meaningful failure classes rather than collapsing everything into generic `ERROR`. fileciteturn2file6L957-L985

Each failure should link to:

```text
trajectory_id
event_id
node_execution_id where applicable
failure_type
structured diagnosis
recovery/intervention
final impact
```

---

# 40. Prototype Acceptance Criteria

A future implementation of this contract should not be considered complete until it can demonstrate at least the following.

### A. Traceability

```text
[ ] request_id exists
[ ] trace_id exists
[ ] trajectory_id exists
[ ] events link to trajectory
[ ] node executions link to plan/version
```

### B. Trajectory reconstruction

```text
[ ] query can be associated with trajectory
[ ] initial plan is visible
[ ] plan changes are visible
[ ] route/node history is visible
[ ] model calls are visible
[ ] retrieval is visible
[ ] tool/action history is visible
[ ] interventions are visible
[ ] final outcome is visible
```

### C. Governance

```text
[ ] permission lineage can be inspected
[ ] consequential actions are attributable
[ ] authorization decisions are linked
[ ] human approval is attributable
[ ] partial execution is explicit
```

### D. Audit semantics

```text
[ ] ledger entries are append-only logically
[ ] historical facts are not silently overwritten
[ ] corrections can be represented explicitly
[ ] private chain-of-thought is not stored
[ ] secrets are not stored
```

### E. Operations

```text
[ ] dashboard can answer what/why/route/failure/intervention/outcome
[ ] analytics can consume trajectory data asynchronously
[ ] persistence failure behavior is defined
[ ] duplicate/out-of-order event behavior is defined
```

### F. Scale

```text
[ ] prototype does not require massive infrastructure
[ ] internal event amplification is considered
[ ] writes can be moved off the critical path where safe
[ ] load tests are defined before scalability claims are made
```

---

# 41. Open Design Questions

These questions should remain explicitly unresolved until answered by the broader architecture or implementation work.

## 41.1 Identifier semantics

- Can a long-lived workflow span multiple requests?
- When should a child trajectory be created?
- How are trajectories linked across multiple agents or applications?

## 41.2 Event ordering

- Is per-trajectory sequence numbering sufficient?
- When is explicit causal linkage required?
- How are late-arriving events reconciled?

## 41.3 Persistence strategy

- What storage abstraction best supports both operational state and historical events?
- Is the prototype's current persistent store sufficient for ledger volume?
- What is the right partitioning/retention strategy as trajectories become longer?

## 41.4 Ledger integrity

- What level of tamper evidence is required for the prototype?
- When does append-only logical behavior need stronger cryptographic guarantees?
- How should signed or externally verifiable exports work in production?

## 41.5 Payload strategy

- Which payloads are stored inline versus by reference?
- What minimum evidence is needed for reconstruction?
- How should payload redaction interact with later investigation?

## 41.6 Privacy

- How should deletion requests interact with immutable governance facts?
- Which identities should be pseudonymized?
- How should field-level sensitivity be enforced in the dashboard?

## 41.7 Replay

- Which workflows require deterministic replay?
- Which external dependencies can be safely simulated?
- How should tool side effects be represented during replay?

## 41.8 Multi-agent lineage

- Should multi-agent execution use one trajectory or parent/child trajectories?
- How should permissions propagate across agent boundaries?
- How should responsibility be attributed when multiple agents contribute to one action?

## 41.9 Availability and governance failure

- Which governance records are mandatory before a high-impact action can continue?
- What is the fail-safe behavior when the ledger is temporarily unavailable?
- Which records may be asynchronously persisted without compromising governance?

## 41.10 Retention

- Which fields require separate retention classes?
- How should policy versions remain reconstructable after policy updates?
- How should model/provider versions remain resolvable after deprecation?

---

# 42. Explicit Non-Goals

This contract must not drift into any of the following:

1. A universal enterprise SIEM replacement.
2. A compliance product with jurisdiction-specific legal guarantees.
3. A private model-internals monitoring system.
4. A storage of private model chain-of-thought.
5. A replacement for the ControlPlane Decision Engine.
6. A replacement for the policy/authorization engine.
7. A replacement for the MCP capability fabric.
8. A generic application logger.
9. A speculative distributed storage architecture optimized for billions of events.

The goal is a clean execution-governance substrate that fits the existing ControlPlane design and can evolve without forcing intelligence logic into infrastructure.

---

# 43. Architecture Invariants

The implementation must preserve these invariants:

### Invariant 1 — Governance unit

For agentic/multi-step execution, the governed unit is the trajectory, not only the final response.

### Invariant 2 — Authority

ControlPlane owns the decision. The Trajectory Store and Execution Ledger provide state/history/evidence.

### Invariant 3 — No chain-of-thought

No private model chain-of-thought is persisted as a governance artifact.

### Invariant 4 — Structured rationale

Decision transparency uses structured rationale, evidence references, policy, confidence, and outcomes.

### Invariant 5 — Permission lineage

Material data access and permission use must be attributable.

### Invariant 6 — Consequential action attribution

Proposed, authorized, and executed consequential actions must be distinguishable.

### Invariant 7 — Plan versioning

Execution changes must remain linked to explicit plan versions.

### Invariant 8 — Partial execution visibility

The system must not hide what happened before a failure, block, or abort.

### Invariant 9 — Append-only ledger semantics

Historical consequential facts are never silently rewritten.

### Invariant 10 — Implementation agnosticism

This contract does not prescribe a database, broker, or storage vendor.

### Invariant 11 — Prototype boundedness

The design must remain appropriate for the stated competition scale and avoid unnecessary infrastructure complexity.

### Invariant 12 — Async analytics where possible

Historical analysis and learning must not unnecessarily block the user-critical control path.

---

# 44. Source Alignment

This document is aligned to the supplied ControlPlane architecture and research direction:

- The high-level architecture defines ControlPlane as a trajectory-governance system and identifies Trajectory Store + Execution Ledger as a first-class subsystem. fileciteturn0file1L10-L46
- The architecture distinguishes Trajectory Store from Execution Ledger and lists the records expected in each. fileciteturn1file3L798-L840
- The runtime governance guidance defines trajectory-level governance and the append-only ledger contract. fileciteturn2file5L806-L914
- The research reference recommends Trajectory Store + Execution Ledger as the backbone for tracking data touched, tools called, permissions used, and external destinations reached. fileciteturn2file3L510-L528
- The scale guidance requires persistent trajectory/execution state and separates critical-path execution from asynchronous observability/analytics. fileciteturn1file0L97-L144

This document intentionally does not infer implementation status from architecture prose. The project's authoritative current-state mechanism requires implementation status to be marked separately as `IMPLEMENTED`, `PARTIAL`, `MOCKED`, `PLANNED`, `EXPERIMENTAL`, `BLOCKED`, or `DEPRECATED`. fileciteturn3file4L791-L819

---

# 45. Required Implementation Contracts

The coding team will eventually need the following interfaces. These are **conceptual contracts**, not final code signatures.

## 45.1 Trajectory Store interface

```text
create_trajectory()
get_trajectory()
update_current_state()
append_trajectory_history()
record_plan_version()
record_node_execution()
record_state_change()
record_evaluation_link()
record_intervention_link()
record_human_review_state()
record_final_outcome()
reconstruct_trajectory()
```

## 45.2 Execution Ledger interface

```text
append_ledger_entry()
append_access_record()
append_permission_record()
append_model_record()
append_retrieval_record()
append_tool_record()
append_action_record()
append_authorization_record()
append_human_approval()
append_intervention()
append_external_destination()
append_verification_result()
append_final_outcome()
get_ledger_for_trajectory()
verify_ledger_consistency()
```

## 45.3 Identifier / correlation interface

```text
create_request_context()
create_or_resolve_trajectory()
create_event_id()
create_node_execution_id()
create_decision_id()
link_trace_context()
```

## 45.4 Event linkage interface

```text
record_event()
link_event_to_trajectory()
link_event_to_node()
link_event_to_plan_version()
link_event_to_decision()
classify_event_as_ledger_relevant()
```

## 45.5 Plan linkage interface

```text
record_plan()
record_plan_version()
get_plan_version()
link_node_to_plan_version()
record_replan_transition()
```

## 45.6 Model invocation interface

```text
record_model_invocation()
link_model_invocation_to_node()
link_model_invocation_to_evaluation()
record_model_result_reference()
```

## 45.7 Retrieval/data-access interface

```text
record_retrieval()
record_source_access()
record_document_access()
record_data_access()
link_evidence_reference()
link_access_to_permission()
```

## 45.8 Permission lineage interface

```text
record_permission_context()
record_permission_grant()
record_permission_use()
record_permission_denial()
link_access_to_permission()
link_agent_to_permission_context()
resolve_lineage_for_trajectory()
```

## 45.9 Tool/action governance interface

```text
record_tool_proposal()
record_tool_authorization()
record_tool_execution()
record_action_proposal()
record_action_authorization()
record_action_execution()
record_external_destination()
record_post_action_verification()
```

## 45.10 Intervention interface

```text
record_intervention()
link_intervention_to_trigger_event()
link_intervention_to_decision()
link_intervention_to_new_plan_version()
record_intervention_outcome()
```

## 45.11 Human approval interface

```text
create_human_review_request()
record_human_decision()
record_human_override()
record_human_timeout()
link_human_decision_to_action_scope()
```

## 45.12 Evaluation/trust interface

```text
record_evaluation()
link_evaluation_to_trajectory()
link_evaluation_to_artifact()
record_risk_signal()
record_confidence_signal()
record_trust_result()
```

## 45.13 Reconstruction interface

```text
reconstruct_trajectory_timeline()
reconstruct_execution_graph()
reconstruct_permission_lineage()
reconstruct_action_history()
reconstruct_decision_history()
reconstruct_final_outcome()
```

## 45.14 Dashboard read interface

```text
get_trajectory_summary()
get_trajectory_timeline()
get_trajectory_graph()
get_decision_history()
get_permission_lineage()
get_interventions()
get_partial_execution_state()
get_final_outcome()
```

## 45.15 Retention/privacy interface

```text
apply_retention_policy()
redact_payload_reference()
mark_sensitive_fields()
resolve_access_permissions()
create_deletion_tombstone()
```

Production versions of these interfaces may be split into separate services or stores, but the conceptual responsibilities should remain stable.

---

# 46. Definition of Done for the Contract

This document is complete when the implementation team can answer, without inventing new architecture, the following questions for one trajectory:

```text
1. What request started it?
2. Which trace and trajectory identifiers belong to it?
3. Which plan version was active at every meaningful transition?
4. Which routes/nodes executed, failed, retried, or were skipped?
5. Which models were invoked?
6. Which retrieval/data/document resources were accessed?
7. Which permissions enabled those accesses?
8. Which tools/actions were proposed, authorized, denied, or executed?
9. What external destinations were reached?
10. What events changed the workflow?
11. What risk/confidence/evaluation signals changed?
12. Why did ControlPlane intervene or replan?
13. Which human approvals or overrides occurred?
14. What partial execution happened before termination?
15. What was finally delivered or executed?
16. What trust/evidence supported the final outcome?
17. Which facts are immutable ledger facts?
18. Which operational state remains mutable?
19. What sensitive data is referenced versus copied?
20. Can a read-only investigator reconstruct the execution without re-running tools?
```

If these questions cannot be answered, the trajectory/ledger contract is incomplete for trajectory-level governance.

---

## 47. Final Architectural Statement

> **The Trajectory Store is the reconstructable execution history of ControlPlane. The Execution Ledger is the append-only record of consequential execution facts. Together they make trajectory-level governance possible across models, retrieval, data, permissions, tools, actions, agents, interventions, human approvals, and final outcomes without storing private model chain-of-thought or turning infrastructure into the decision-making brain.**

This subsystem is therefore the state-and-evidence backbone that allows ControlPlane to govern not merely what an AI system says, but **what it did, what it touched, what it was allowed to do, what changed during execution, and how the final outcome was reached**.
