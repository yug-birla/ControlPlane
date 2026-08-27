# ControlPlane.ai — Runtime Flow

**Status:** Canonical Runtime Specification  
**Scope:** Lifecycle of a single ControlPlane request  
**Audience:** ControlPlane core, planner, policy, capability, evaluation, intervention/replanning, observability, audit, and learning workstreams

> **This document specifies runtime behavior. It is not an algorithm document.**
>
> It defines the canonical lifecycle, control boundaries, state transitions, and decision points for one request. It deliberately does not select specific ML algorithms, model families, retrieval algorithms, risk formulas, or event-bus technologies.

---

## 1. Purpose

ControlPlane.ai governs the execution trajectory of an AI workflow rather than merely inspecting its final message.

For a single request, the canonical runtime is:

```text
USER
  ↓
API
  ↓
Query Intelligence
  ↓
Policy
  ↓
Capability Discovery
  ↓
Initial Plan
  ↓
Execution Graph
  ↓
Capability Execution
  ↓
Trajectory / Ledger
  ↓
Evaluation
  ↓
Risk / Confidence
  ↓
Decision
  ↓
Intervention / Replanning
  ↓
Verification
  ↓
Output
  ↓
Async Observability
  ↓
Learning
```

The loop is not necessarily linear after execution begins. New evidence, failures, policy findings, trajectory changes, or uncertainty may cause the ControlPlane to re-enter planning, evaluation, intervention, or verification.

```text
                         ┌────────────────────────────────┐
                         │                                │
                         ▼                                │
USER → API → UNDERSTAND → POLICY → DISCOVER → PLAN → EXECUTE
                                                      │
                                                      ▼
                                               OBSERVE STATE
                                                      │
                                                      ▼
                                                  EVALUATE
                                                      │
                                                      ▼
                                               RISK / CONFIDENCE
                                                      │
                                                      ▼
                                                   DECIDE
                                                      │
                                  ┌───────────────────┼──────────────────┐
                                  │                   │                  │
                               CONTINUE            INTERVENE          ESCALATE
                                  │                   │                  │
                                  │              REPLAN/REPAIR       HUMAN/ABSTAIN
                                  │                   │                  │
                                  └───────────────→ VERIFY ←─────────────┘
                                                      │
                                                      ▼
                                                    OUTPUT
                                                      │
                                                      ▼
                                             ASYNC OBSERVABILITY
                                                      │
                                                      ▼
                                                   LEARNING
```

The central authority remains **ControlPlane Core**:

```text
ControlPlane Core
= intelligence + state + policy + decision + replanning

Execution Graph
= what should happen

Event Bus
= what happened / what changed

MCP Capability Fabric
= how capabilities are discovered and invoked
```

MCP is therefore a capability fabric, not the brain.

---

## 2. Runtime Responsibilities and Boundaries

### 2.1 Deterministic runtime responsibilities

The following are runtime contracts and must not depend on a particular intelligent algorithm:

- establish request and trace identity;
- bind application, user/session, and policy context;
- maintain authoritative execution state;
- preserve plan versions;
- enforce dependency ordering in the execution graph;
- record consequential execution facts;
- route structured events to the ControlPlane decision process;
- preserve trajectory and ledger history;
- enforce explicit policy outcomes;
- prevent unauthorized capability execution;
- honor budgets, bounded retries, pauses, and terminal states;
- expose final status, trust information, evidence references, limitations, and relevant execution history.

### 2.2 Pluggable intelligent responsibilities

The following are intentionally replaceable:

- query profiling;
- capability selection;
- plan generation;
- quality evaluation;
- factuality/grounding evaluation;
- reasoning evaluation;
- risk estimation;
- confidence estimation;
- behavioral drift assessment;
- intervention selection;
- replan proposal;
- verification strategy;
- learning methods.

The runtime consumes their normalized outputs; it does not require one specific algorithm.

### 2.3 Capability boundary

Capabilities may include models, SQL, RAG, web/search, memory, chat databases, verifiers, enterprise APIs, and agent tools.

A capability may:

- execute an authorized step;
- return a result;
- report evidence;
- report failure;
- emit a structured event;
- report a limitation or uncertainty.

A capability must not independently decide which other capability should run next.

The forbidden pattern is:

```text
RAG Route → SQL Route
```

The canonical pattern is:

```text
RAG
  ↓
DATA_REQUIRED event
  ↓
Event Bus
  ↓
ControlPlane Decision
  ↓
Replan
  ↓
SQL
```

---

## 3. Request Lifecycle

Each request moves through the following conceptual stages.

| Stage | Runtime purpose | Primary authority | Typical state effect |
|---|---|---|---|
| API | establish request boundary and context | ControlPlane | creates request/trace context |
| Query Intelligence | build provisional request fingerprint | ControlPlane + intelligence component | writes query profile |
| Policy | determine governing constraints | ControlPlane Policy | establishes policy context and constraints |
| Capability Discovery | identify available/authorized capabilities | ControlPlane using capability fabric | records candidate capabilities |
| Initial Plan | construct first execution strategy | ControlPlane planner | creates plan version |
| Execution Graph | represent current strategy | ControlPlane runtime | creates executable graph state |
| Capability Execution | perform model/data/tool work | authorized capability | updates step/result state; emits events |
| Trajectory/Ledger | reconstruct workflow and consequential facts | ControlPlane state layer | records trajectory and ledger facts |
| Evaluation | judge quality/risk-relevant properties | pluggable evaluators | writes evaluation results |
| Risk/Confidence | maintain separate governance signals | ControlPlane + pluggable signals | updates risk/confidence state |
| Decision | choose next permitted action | ControlPlane Decision Engine | records decision |
| Intervention/Replanning | change strategy or control autonomy | ControlPlane | creates intervention/replan state |
| Verification | establish release/action readiness | ControlPlane + verification capability | updates trust/verification state |
| Output | release best trustworthy result or safe terminal state | ControlPlane | finalizes response/status |
| Async Observability | persist and aggregate non-critical telemetry | event consumers | history/metrics/audit views |
| Learning | improve future control decisions | offline/asynchronous learning loop | feedback/route/risk/evaluation signals |

The exact number of internal iterations is workload-dependent. A request may traverse the execution/evaluation/decision loop zero, one, or multiple times before reaching a terminal outcome.

---

## 4. Critical Synchronous Path

The user-critical path contains only work needed to safely and correctly determine the response or external action.

```text
USER
 ↓
API / Gateway
 ↓
Query Intelligence
 ↓
Required Policy Context
 ↓
Capability Discovery
 ↓
Initial Plan
 ↓
Execution Graph
 ↓
Capability Execution
 ↓
State + Trajectory + Ledger Update
 ↓
Required Evaluation
 ↓
Risk / Confidence
 ↓
Decision
 ├── continue ────────────────┐
 ├── intervene / replan ──────┤
 ├── human review ────────────┤
 ├── abstain / block ─────────┤
 └── terminal failure ────────┤
                              ▼
                         Verification
                              ↓
                            Output
```

### 4.1 Keep on the synchronous path when required

- request profiling required for routing or policy;
- policy evaluation required to authorize the current step;
- execution of the selected capability;
- critical state and trajectory updates;
- evaluation required for the decision;
- intervention or replanning required to produce a safe/better result;
- human approval when policy requires it;
- critical verification required before response release or external action;
- final output construction.

### 4.2 Do not block the user path unnecessarily

The following should normally be asynchronous unless a specific runtime contract makes them decision-critical:

- dashboard aggregation;
- long-term analytics;
- route statistics;
- benchmark aggregation;
- offline evaluation;
- trend analysis;
- learning updates;
- non-critical telemetry enrichment.

The architecture must not become a giant synchronous chain merely to make observability or analytics appear immediate.

---

## 5. Asynchronous Path

After enough information exists to produce the user-visible result, non-critical work may continue asynchronously.

```text
                         USER
                          │
                          ▼
                 Final ControlPlane Result
                          │
                          ▼
                        OUTPUT
                          │
                 ┌────────┴────────┐
                 │                 │
                 ▼                 ▼
           user response      event stream
                                   │
                ┌──────────────────┼────────────────────┐
                ▼                  ▼                    ▼
             history           metrics              analytics
                │                  │                    │
                └──────────────────┼────────────────────┘
                                   ▼
                              evaluation history
                                   │
                                   ▼
                                learning
```

Async consumers must not alter the already released response unless the product explicitly defines a post-response correction mechanism. They may update historical, analytical, or learning records.

Async processing must preserve request, trace, trajectory, event, plan-version, and causal references sufficient to reconstruct the runtime.

---

## 6. Runtime State Model

The request has authoritative mutable execution state. At minimum it must be able to represent:

```text
request_id
trace_id
trajectory_id
query
query_profile
policy_context
capability_context
current_plan
plan_version
current_step
completed_steps
pending_steps
blocked_steps
evidence
risk_state
confidence_state
behavioral_drift_state
models_used
retrieval_used
tools_used
permissions
data_accessed
external_destinations
cost
latency
events
interventions
human_review_state
verification_state
final_answer
trust_report
final_status
```

### 6.1 State authority

- **ControlPlane state** is authoritative for current runtime decisions.
- **Trajectory Store** is the reconstructable workflow history/context.
- **Execution Ledger** is the append-only record of consequential facts.
- **Events** are immutable observations/facts about execution.
- **Plan versions** define the strategy that was authoritative at a particular point in time.

These records are related but not interchangeable.

```text
Capability observation
        │
        ▼
      Event
        │
        ├────────→ Event History
        │
        ├────────→ Execution Ledger (when consequential)
        │
        ▼
ControlPlane interpretation
        │
        ▼
State transition
        │
        ▼
Decision / New plan version
```

### 6.2 State update rule

A capability does not directly mutate another capability's control state. It reports normalized facts/results through the runtime interface. The ControlPlane interprets those facts against the current state and policy.

---

## 7. Query Intelligence

Query Intelligence produces a **provisional multi-dimensional Query Fingerprint**.

It should capture, where applicable:

```text
intent
domain
data_requirements
complexity
sensitivity
impact
actionability
risk_vector
```

Risk dimensions may include factuality, hallucination, reasoning, privacy/PII, security, bias, compliance, financial, action, and reputational concerns.

The profile is provisional.

```text
Initial profile
      ↓
Execution evidence
      ↓
Possible reclassification
      ↓
Updated profile / policy context
```

A later event may show that a request is more complex, more sensitive, more consequential, or more data-dependent than originally estimated.

The runtime must allow that change without treating the initial classifier output as an irreversible routing decision.

---

## 8. Policy Evaluation

Policy is context-dependent. Runtime policy may depend on:

```text
application
domain
jurisdiction
risk appetite
user role
sensitivity
actionability
verification requirements
human-review requirements
cost/latency constraints
allowed capabilities
```

Policy determines what is permitted; it does not merely score the result.

Policy may constrain:

- which capabilities can be selected;
- which data may be accessed;
- which permissions may be used;
- what level of verification is required;
- whether an action needs human approval;
- whether a workflow must abstain or block;
- whether degraded operation is permitted.

Policy decisions must remain attributable to the relevant policy context/version.

---

## 9. Capability Discovery

Before planning, ControlPlane discovers or reads the set of capabilities available to the request.

Capability descriptors may contain:

```text
capability_id
type
supported_tasks
input_schema
output_schema
latency_class
cost_class
risk_class
authorization_requirements
supports_parallel
availability
```

Capability discovery answers:

> **What can be used under the current request, policy, permissions, budgets, and environment?**

It does not answer:

> **What should happen next?**

That remains a ControlPlane planning/decision responsibility.

---

## 10. Initial Planning

The Initial Planner converts:

```text
Query Fingerprint
+
Policy Context
+
Available Capabilities
+
Budgets / Constraints
+
Current State
```

into an **Initial Execution Plan**.

A plan is a first-class, versioned object. Conceptually it contains:

```text
plan_id
plan_version
steps
dependencies
parallel_groups
required_capabilities
verification_level
allowed_tools
human_approval
cost_budget
latency_budget
fallbacks
```

The plan is provisional.

### 10.1 Planning rule

The first plan should be the best currently supported execution strategy, not a commitment to a fixed route.

```text
Plan v1
   ↓
execute
   ↓
new evidence
   ↓
ControlPlane decision
   ↓
Plan v2 (if required)
```

A replan creates a new plan version. Historical events keep their original plan-version linkage.

---

## 11. Execution Graph

The current plan is represented as a mutable execution graph.

The graph must support runtime changes such as:

```text
add node
remove node
skip node
retry node
replace node
switch capability/model
change retrieval
increase/decrease reasoning budget
insert verifier
pause
resume
human review
terminate
```

### 11.1 Sequential dependencies

A dependency exists when a later step requires information or state produced by an earlier step.

Example:

```text
Retrieve Policy Documents
          ↓
   Evidence Available
          ↓
    Reasoning Step
          ↓
       Verify
```

The dependent step must not run before its prerequisite reaches an allowed terminal state.

A failure in an upstream step may therefore block, skip, replace, or replan downstream work.

### 11.2 Parallel execution

Parallelism is a **planning decision**, not a default.

Use parallel execution only when:

- the branches are independent enough to execute concurrently;
- dependencies permit concurrency;
- policy permits the required capability accesses;
- the latency benefit is meaningful;
- added cost and risk are acceptable.

Example:

```text
                Query
                  ↓
             ControlPlane
                  ↓
          ┌───────┼───────┐
          ↓       ↓       ↓
         SQL     RAG    Memory
          │       │       │
          └───────┼───────┘
                  ↓
            Evidence Merge
                  ↓
              Reasoning
                  ↓
             Verification
```

Do not fan out to every available capability. The planner selects the smallest useful set.

### 11.3 Synchronization

A synchronization point exists when downstream work depends on multiple parallel branches.

```text
     ┌→ SQL ────┐
     │          │
Query┼→ RAG ────┼→ Merge → Reason → Verify
     │          │
     └→ Memory ─┘
```

The merge must preserve branch provenance and evidence references so later evaluation can distinguish sources and conflicts.

---

## 12. Capability Execution

Execution occurs through authorized capabilities.

Canonical interaction:

```text
ControlPlane
   ↓
Capability Request
   ↓
MCP Adapter / Capability Interface
   ↓
MCP Server or Internal Capability
   ↓
Capability
   ↓
Normalized Result
   ↓
Execution State + Event Bus
```

MCP provides interoperability and invocation. It does not choose the next route.

For an agentic action:

```text
Agent proposal
      ↓
ControlPlane action-risk/policy check
      ↓
ALLOW / MODIFY / HUMAN / BLOCK
      ↓
Authorized execution
      ↓
Post-action verification
```

No agent should bypass ControlPlane policy to directly convert model output into an external consequential action.

---

## 13. Event Emission

Events are structured observations of what happened or changed.

An event should be traceable to, where applicable:

```text
event_id
request_id
trace_id
trajectory_id
timestamp
source
event_type
severity
plan_id
plan_version
step_id
capability/model/route identifier
confidence
risk/evaluation context
evidence references
metadata
```

Useful runtime event classes include:

```text
QUERY_RECEIVED
QUERY_PROFILED
QUERY_RECLASSIFIED
RISK_DETECTED
ROUTE_SELECTED
RETRIEVAL_STARTED
RETRIEVAL_COMPLETED
DATA_REQUIRED
DATA_UNAVAILABLE
RETRIEVAL_INSUFFICIENT
EVIDENCE_CONFLICT
MODEL_CALLED
MODEL_DISAGREEMENT
HIGH_REASONING_UNCERTAINTY
TOOL_CALLED
TOOL_COMPLETED
TOOL_FAILURE
PERMISSION_ESCALATION
PII_DETECTED
PRIVACY_RISK
HIGH_ACTION_RISK
BEHAVIORAL_DRIFT_HIGH
EVALUATION_COMPLETED
VERIFICATION_FAILED
INTERVENTION_TRIGGERED
REPLAN_TRIGGERED
PLAN_UPDATED
HUMAN_REVIEW_REQUIRED
FINAL_RESPONSE_GENERATED
```

### 13.1 Event versus command

Events say:

> **What happened / what was observed.**

Commands say:

> **What should happen next.**

The event bus must not contain hidden commands such as:

```text
MODEL_FAILURE → call Model B
```

Instead:

```text
MODEL_FAILURE event
      ↓
ControlPlane interprets state + policy + budgets + evidence
      ↓
Decision
      ↓
Intervention / Replan
```

### 13.2 Event semantics and state

If an observation can materially affect runtime behavior, it must be represented explicitly enough for the ControlPlane to interpret it.

Important state changes must not exist only in unstructured logs.

---

## 14. Trajectory and Execution Ledger Updates

The trajectory is the unit of runtime governance for multi-step, tool-using, stateful, and agentic workflows.

At minimum, the trajectory should preserve, where applicable:

```text
trajectory_id
request_id
trace_id
principal / user identity
application identity
policy context
current risk state
current confidence state
current plan/version
execution steps
data touched
permissions acquired
models invoked
retrieval performed
tools invoked
external destinations
intermediate state changes
interventions
human approvals/overrides
final outcome
```

### 14.1 Trajectory Store

```text
Trajectory Store
= reconstructable current + historical workflow context
```

It supports recovery, replay, inspection, and replanning.

### 14.2 Execution Ledger

```text
Execution Ledger
= append-only consequential execution facts
```

It should record, where applicable:

```text
data accessed
permissions used/acquired
models invoked
tools called
actions proposed
actions authorized
actions executed
external destinations reached
policy decisions
risk/confidence decisions
interventions
human overrides
```

Ledger facts must not be silently rewritten.

### 14.3 Lineage

For sensitive data and consequential actions, retain enough lineage to answer:

```text
Who/what requested it?
What data was accessed?
Under which permission?
For what trajectory/purpose?
Where did the data flow next?
Which model/agent/tool received it?
Which external destination received it?
```

This is required to prevent permission laundering across agents and capabilities.

---

## 15. Evaluation

Evaluation is modular and policy-selected.

Potential evaluator interfaces include:

```text
QualityEvaluator
FactualityEvaluator
GroundingEvaluator
ReasoningEvaluator
SafetyEvaluator
PrivacyEvaluator
PIIEvaluator
BiasEvaluator
SecurityEvaluator
CostEvaluator
LatencyEvaluator
ActionRiskEvaluator
ConsistencyEvaluator
```

An evaluator returns structured findings, conceptually:

```text
score
confidence
issues
evidence
recommended_action
```

The architecture does not prescribe the algorithm used to obtain these fields.

Evaluation may examine:

- answer quality;
- grounding/evidence adequacy;
- reasoning sufficiency;
- safety/privacy/security;
- cost/latency behavior;
- action risk;
- cross-result consistency;
- policy compliance.

Evaluation is an input to ControlPlane decision-making, not a replacement for it.

---

## 16. Risk

Risk is a first-class runtime state and, for agentic workflows, is a property of the trajectory rather than only the latest message.

Relevant dimensions may include:

```text
factuality
hallucination
reasoning
privacy / PII
security
bias
compliance
financial risk
action risk
reputational risk
trajectory / composition risk
```

For agentic workflows, runtime decisions must consider:

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
```

Risk and confidence must remain separate fields.

```text
high risk ≠ low confidence
low risk ≠ high confidence
```

Risk thresholds are policy/configuration, not hard-coded architecture.

---

## 17. Confidence

Confidence is a decision signal describing how strongly the current execution state supports the relevant conclusion.

It may incorporate evidence from:

- evaluator outputs;
- evidence quality;
- model disagreement;
- verification state;
- retrieval adequacy;
- uncertainty signals;
- observed execution behavior.

The runtime must not present heuristic confidence as a calibrated probability unless calibration has been demonstrated.

Confidence cannot override hard policy.

For example:

```text
High confidence
+ high-risk action
≠ automatically safe
```

A high-confidence result can still require human review or blocking if policy requires it.

---

## 18. Behavioral Drift

For agentic or long-running trajectories where drift monitoring is justified, maintain an interpretable **Behavioral Drift Score** as a governance signal.

Candidate signals include:

```text
tool-use velocity deviation
data-source deviation
action-sensitivity deviation
trajectory-length deviation
monetary/value deviation
permission-scope deviation
external-destination deviation
```

Conceptually:

```text
Expected trajectory
        vs
Actual trajectory
        ↓
Behavioral Drift
```

Drift should trigger reassessment of:

```text
risk
confidence
policy applicability
allowed capabilities
verification level
need for intervention
```

Drift alone is not an automatic block unless policy explicitly makes it one.

---

## 19. Decision Engine

The Decision Engine is the central runtime authority.

It combines:

```text
current state
+
plan/version
+
events
+
evidence
+
risk
+
confidence
+
behavioral drift
+
policy
+
permissions
+
cost budget
+
latency budget
+
capability availability
```

It chooses the next permitted outcome.

### 19.1 Decision matrix

The baseline policy uses a Risk × Confidence matrix with four primary governance outcomes:

| Risk | Confidence | Baseline outcome |
|---|---|---|
| Low | High | **PASS** |
| Low / Moderate | Uncertain | **MONITOR** |
| High | High | **Policy-specific controls; do not treat confidence as safety** |
| High | Low | **ESCALATE or BLOCK** |

The matrix is a governance abstraction. Exact thresholds remain configurable.

The runtime may also decide to:

```text
CONTINUE
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
MONITOR
ESCALATE
HUMAN_REVIEW
BLOCK
ABORT
ABSTAIN
```

The Decision Engine must be the component that selects among these outcomes. No capability may bypass it for a consequential route transition.

---

## 20. Intervention

An intervention is a bounded ControlPlane action taken because the current execution is no longer the best or safest permitted path.

Canonical sequence:

```text
Failure / uncertainty / drift / risk signal
                ↓
              Event
                ↓
       ControlPlane evaluation
                ↓
            Decision
                ↓
     INTERVENTION_TRIGGERED
                ↓
        bounded intervention
                ↓
       updated execution state
                ↓
        continue / replan / verify
```

Interventions may include:

```text
retry
regenerate
reroute
retrieve
change retrieval
change model
increase/decrease reasoning
verify
repair
redact
ask clarification
abstain
escalate
human review
block
abort
```

### 20.1 Intervention bounds

Self-healing must never mean “retry until something passes.”

Every intervention remains bounded by:

- policy;
- available evidence;
- maximum retries;
- risk threshold;
- latency budget;
- cost budget;
- capability availability;
- human-approval requirements.

---

## 21. Replanning

Replanning occurs when the current plan is no longer the best or safest strategy under the newly observed state.

```text
Plan v1
  ↓
Execution
  ↓
New evidence/event
  ↓
Decision: current plan no longer appropriate
  ↓
REPLAN_TRIGGERED
  ↓
Replanner proposes graph changes
  ↓
ControlPlane accepts a new authoritative plan
  ↓
PLAN_UPDATED
  ↓
Plan v2
  ↓
Execution resumes
```

### 21.1 Plan version rules

1. Events do not mutate historical plan versions.
2. Every replan creates a new plan version.
3. The triggering event references the old plan version.
4. `REPLAN_TRIGGERED` records why the strategy must change.
5. `PLAN_UPDATED` records the new authoritative version.
6. New execution steps reference the new plan version.
7. Historical events preserve their original linkage.

This is required to answer:

> **Why did ControlPlane choose a different execution path?**

---

## 22. Self-Healing

Self-healing is:

> **Detect failure → diagnose → choose bounded intervention → modify execution → verify.**

Different diagnoses can result in different interventions.

```text
QUERY_FAILURE
→ clarify / reprofile / replan / abstain

DATA_FAILURE
→ alternate permitted source / abstain

RETRIEVAL_FAILURE
→ alternate retrieval / retrieve differently / verify / abstain

MODEL_FAILURE
→ retry / change capability / replan

REASONING_FAILURE
→ stronger reasoning capability / verification / escalate

EVIDENCE_FAILURE
→ retrieve / verify / abstain

POLICY_FAILURE
→ modify request path / human review / block

TOOL_FAILURE
→ alternate capability / retry within bounds / safe degradation

RESOURCE_FAILURE
→ alternate permitted resource / reduce scope / defer / abstain
```

The taxonomy must preserve diagnosis. A generic `ERROR` is not sufficient when a meaningful failure class is known.

---

## 23. Human Review

Human review is an explicit runtime control state, not an unstructured failure message.

Canonical flow:

```text
ControlPlane detects condition requiring human judgment
                         ↓
              HUMAN_REVIEW_REQUIRED
                         ↓
                 execution paused
                         ↓
        human receives required context
                         ↓
       APPROVE / MODIFY / REJECT / ESCALATE
                         ↓
             ControlPlane records decision
                         ↓
       resume / replan / block / abort / abstain
```

The review record must preserve:

```text
reason for review
relevant evidence
active plan/version
risk/confidence context
proposed action or response
human decision
timestamp
override information
resulting state transition
```

For high-impact actions, the absence of required human approval is not equivalent to approval.

---

## 24. Graceful Degradation

When a dependency or governance capability is unavailable, the system should degrade progressively rather than either failing open or immediately blocking everything.

Conceptual sequence:

```text
full capability
    ↓
reduced capability
    ↓
reduced autonomy
    ↓
stronger verification
    ↓
human review
    ↓
safe abstention / block
```

Examples:

```text
Verifier unavailable
→ alternate verifier
→ bounded reduced verification
→ human review for high-impact cases
→ abstain/block if required

Tool unavailable
→ alternate permitted capability
→ draft-only mode
→ no external execution
```

Graceful degradation is always policy-bounded. It never means “continue regardless of risk.”

---

## 25. Abstention

Abstention is a successful terminal outcome when the system cannot establish a sufficiently trustworthy or authorized path.

Abstention may be required when:

- evidence is insufficient;
- required data is missing or inaccessible;
- sources conflict;
- authorization is unclear;
- risk exceeds policy tolerance;
- human judgment is required and unavailable;
- verification fails;
- the remaining path would violate cost/latency/risk constraints;
- no permitted recovery path remains.

Canonical terminal state:

```text
ABSTAINED
```

A trustworthy abstention is preferable to an unsupported answer or unauthorized action.

---

## 26. Agentic Path

Agentic workflows require trajectory-level control.

### 26.1 Runtime sequence

```text
Request
  ↓
Query Intelligence
  ↓
Policy / Capability Discovery
  ↓
Agent Plan / Proposal
  ↓
ControlPlane decision
  ↓
Tool / capability proposal
  ↓
Trajectory + permission + action-risk evaluation
  ↓
ALLOW / MODIFY / HUMAN / BLOCK
  ↓
Execute authorized action
  ↓
Record ledger fact
  ↓
Evaluate result
  ↓
Update trajectory
  ↓
Continue / intervene / replan
  ↓
Final verification
```

### 26.2 Intervention points

ControlPlane should have meaningful control points:

```text
before planning
before sensitive data access
before permission expansion
before tool invocation
before external write/action
after consequential tool result
after material risk/drift increase
after disagreement
before cross-agent state transfer
before final release
after partial execution
```

### 26.3 Partial execution

Action state must distinguish at least:

```text
PROPOSED
AUTHORIZED
EXECUTING
COMPLETED
PARTIALLY_COMPLETED
FAILED
BLOCKED
ABORTED
```

Where compensation or rollback exists, the runtime must record its status and never claim success without external confirmation.

If an irreversible action occurred before a later failure, the trajectory remains visibly partial. The runtime proceeds through containment, compensation where available, human review, replan, or safe termination rather than pretending the workflow rolled back.

---

## 27. Multi-Agent Path

Multi-agent execution must track composition and lineage across agents.

At minimum:

```text
agent identity
parent / child relationship
shared state transferred
permissions inherited/transferred
data received from another agent
tools/actions proposed
cumulative action impact
external destinations
```

The ControlPlane evaluates aggregate trajectory state.

### 27.1 Permission laundering

A prohibited pattern is:

```text
Agent A
  ↓ cannot access sensitive data
Agent B
  ↓ has access
Sensitive data
  ↓
Agent B → Agent A
  ↓
Agent A → external destination
```

The overall trajectory must still be evaluated against the originating authorization and data policy.

### 27.2 Composition risk

Individually permitted actions may become impermissible in combination.

```text
Agent A result
      ↓
Agent B transformation
      ↓
Agent C action
      ↓
Aggregate impact exceeds policy
      ↓
ControlPlane intervention
```

The ControlPlane therefore tracks both local and cumulative risk.

---

## 28. Verification

Verification is the final control before release or consequential action.

It is not required to be identical for every request.

The verification level should reflect:

```text
risk
confidence
impact
sensitivity
trajectory state
policy
failure history
replanning history
```

Possible outcomes:

```text
VERIFIED
VERIFIED_WITH_LIMITATIONS
REQUIRES_REVIEW
FAILED
UNVERIFIABLE
```

Verification should use structured evidence and preserve references to the checks that informed the release decision.

A failed verification must not be silently ignored.

```text
Verification failed
      ↓
Event
      ↓
ControlPlane decision
      ↓
Replan / intervene / human / abstain
```

---

## 29. Final Output

The output is the **best available trustworthy result permitted by policy**, not merely the raw result of the first model/capability.

The runtime may return:

```text
answer
+
trust assessment
+
evidence references
+
limitations
+
relevant action/execution information
+
final status
```

### 29.1 Trust report

Trust should be evidence-backed and understandable.

Example structure:

```text
TRUST: HIGH

Why:
- supported by authorized evidence
- required verification passed
- no unresolved material disagreement
- source state is sufficiently current

Limitations:
- data availability boundary
- unresolved assumptions
```

Low trust must be explicit:

```text
TRUST: LOW

Why:
- required evidence unavailable
- retrieved context incomplete
- material disagreement remains

ControlPlane action:
- unsupported information was not presented as fact
```

Do not fabricate a precise confidence/trust probability without a justified calibrated method.

---

## 30. History and Auditability

A completed request must leave sufficient records to answer:

```text
What was asked?
What was the initial profile?
Which policy applied?
Which capabilities were available?
What was the initial plan?
Which plan versions existed?
What executed?
What data was accessed?
Which permissions were used?
What events occurred?
What failed?
What evaluations ran?
What risk/confidence state existed?
What interventions occurred?
Why was the plan changed?
Was human review involved?
What was verified?
What was returned?
What trust/limitations were reported?
What did it cost?
How much latency did it add?
```

History should distinguish at least:

```text
Query History
Route / Plan History
Decision History
Execution Trace
Event History
Trajectory History
Ledger History
Intervention History
Human Review History
Evaluation History
```

The runtime should store a **decision trace**, not private chain-of-thought.

A decision trace explains the observable control decision:

```text
Decision:
REROUTE

Reason:
Current route produced insufficient evidence.

Evidence:
retrieval evaluation + policy context

Constraints:
cost budget preserved; policy permits alternate retrieval

Prior plan:
v1
New plan:
v2
```

---

## 31. Learning

Learning occurs primarily after the user-critical path.

A completed execution contributes:

```text
query
query profile
policy context
plan versions
trajectory
events
evaluations
risk/confidence
interventions
outcome
feedback
cost
latency
trust
```

These records can support future improvement of:

```text
query profiling
capability/model routing
risk assessment
evaluation selection
intervention selection
replanning quality
model capability profiles
verification selection
```

The runtime specification does not mandate online learning. The architecture only requires preservation of the information needed to support future learning and evaluation.

Learning must not silently rewrite historical execution facts.

---

## 32. Fast Path

Fast Path is a runtime governance mode for simple, low-risk requests where impact, sensitivity, and uncertainty are limited.

### Eligibility characteristics

Typical signals:

```text
low impact
low risk
high enough confidence
limited data sensitivity
no consequential external action
simple execution graph
```

### Canonical flow

```text
USER
 ↓
API
 ↓
light profiling
 ↓
policy/risk check
 ↓
capability discovery
 ↓
fast capability
 ↓
lightweight verification
 ↓
trust/output
 ↓
USER
```

Fast Path must still preserve the normal request/trace identity and enough state to explain what happened.

Fast Path is not a bypass around ControlPlane governance.

---

## 33. Deep Path

Deep Path is a runtime governance mode for requests that are high-risk, high-complexity, high-impact, sensitive, agentic, materially uncertain, or otherwise outside the safe envelope of Fast Path.

### Trigger characteristics

```text
high impact
high risk
low/uncertain confidence
complex reasoning
enterprise data dependency
agentic execution
multi-agent composition
material behavioral drift
consequential external action
verification failure
trajectory deviation
```

### Canonical flow

```text
USER
 ↓
API
 ↓
detailed profiling
 ↓
policy + risk/confidence
 ↓
capability discovery
 ↓
detailed plan
 ↓
trajectory/ledger initialization
 ↓
execution graph
 ↓
execution
 ↓
continuous evaluation
 ↓
risk/confidence/drift update
 ↓
decision
 ├── continue
 ├── intervene
 ├── replan
 ├── human review
 ├── graceful degradation
 ├── abstain
 └── block
 ↓
verification
 ↓
trust/output
 ↓
USER
```

The request may transition dynamically from Fast Path to Deep Path when new evidence increases risk/complexity or reduces confidence.

---

## 34. Shadow Mode

Shadow Mode allows ControlPlane to observe and log what it **would** have done without enforcing that decision on the runtime path, except where a separately configured hard safety boundary must still apply.

```text
Actual application path
        │
        ├──────────────→ user-visible execution
        │
        ▼
   ControlPlane Shadow
        │
        ├── profile
        ├── evaluate
        ├── risk/confidence
        ├── proposed decision
        ├── proposed intervention
        └── evidence
```

Shadow Mode requirements:

- mode must be explicit in configuration and telemetry;
- proposed decisions must be distinguishable from executed interventions;
- shadow observations are recorded in trajectory/history where applicable;
- shadow mode cannot be misrepresented as enforcement;
- shadow results can be compared against actual outcomes for evaluation.

Shadow Mode is appropriate for validating governance behavior before enabling enforcement.

---

## 35. Enforcement Mode

Enforcement Mode allows ControlPlane decisions to govern execution.

```text
Observation
   ↓
Evaluation
   ↓
Risk / Confidence
   ↓
Policy
   ↓
Decision
   ↓
INTERVENE / ALLOW / HUMAN / BLOCK / ABSTAIN
   ↓
Execution consequence
```

In Enforcement Mode:

- policy decisions can modify or stop execution;
- tool/action requests may be held for approval;
- the execution graph may be changed;
- unsafe or unsupported paths can be blocked or aborted;
- trust and verification requirements must be honored.

Enforcement decisions must be recorded with their reason and evidence references.

---

## 36. Canonical Request Sequence Diagram

```text
User        API       ControlPlane       MCP/Capabilities      Evaluators       Human
 │           │              │                    │                  │             │
 │ request   │              │                    │                  │             │
 ├──────────>│              │                    │                  │             │
 │           │ create ids   │                    │                  │             │
 │           ├─────────────>│                    │                  │             │
 │           │              │ profile            │                  │             │
 │           │              │ policy              │                  │             │
 │           │              │ discover            │                  │             │
 │           │              │ plan v1             │                  │             │
 │           │              │ graph               │                  │             │
 │           │              ├───────────────────>│                  │             │
 │           │              │    result/event     │                  │             │
 │           │              │<───────────────────┤                  │             │
 │           │              │ state/trajectory    │                  │             │
 │           │              ├───────────────────────────────────────>│             │
 │           │              │                       evaluation        │             │
 │           │              │<───────────────────────────────────────┤             │
 │           │              │ risk/confidence      │                  │             │
 │           │              │ decision             │                  │             │
 │           │              ├────────────────────────────────────────────────────>│
 │           │              │                                       review         │
 │           │              │<────────────────────────────────────────────────────┤
 │           │              │ replan/continue     │                  │             │
 │           │              ├───────────────────>│                  │             │
 │           │              │ verification         │                  │             │
 │           │              │ output               │                  │             │
 │<──────────┤              │                    │                  │             │
 │ response  │              │                    │                  │             │
 │           │              │──── async events / history / learning ──────────────>│
```

---

## 37. Example Flow 1 — Simple Factual Request

### Goal

A low-risk factual request with no sensitive data, external action, or enterprise-data requirement.

```text
User
 ↓
API
 ↓
Query Intelligence
 → factual lookup
 → low complexity
 → low impact
 ↓
Policy
 → no special constraints
 ↓
Capability Discovery
 → suitable fast capability
 ↓
Fast Path plan v1
 ↓
Execute
 ↓
Light evaluation / verification
 ↓
Risk = low
Confidence = sufficient
 ↓
Decision = PASS
 ↓
Trust report
 ↓
Answer
 ↓
Async history / metrics / learning
```

No deep verification or expensive capability should be added solely because it exists.

---

## 38. Example Flow 2 — Enterprise SQL Request

### Goal

An enterprise quantitative question where authoritative structured data exists.

```text
User
 ↓
API
 ↓
Query Intelligence
 → analytical / enterprise
 → SQL data requirement
 → potentially decision-support
 ↓
Policy
 → authorized enterprise data scope
 ↓
Capability Discovery
 → enterprise SQL
 → reasoning/explanation capability
 → verification capability
 ↓
Plan v1
 SQL → explanation → verify
 ↓
Execution
 SQL query
 ↓
Deterministic result
 ↓
Trajectory/Ledger
 → data accessed
 → permission context
 → query/result metadata
 ↓
Evaluation
 → correctness / policy / evidence
 ↓
Risk + Confidence
 ↓
Decision = continue
 ↓
Explanation
 ↓
Verification
 ↓
Trust report + source/evidence references
 ↓
Answer
```

The runtime must prefer the authoritative deterministic enterprise source when one exists rather than treating the LLM as the quantitative source of truth.

---

## 39. Example Flow 3 — Insufficient RAG → Replan

```text
User
 ↓
Query Intelligence
 → enterprise document/RAG requirement
 ↓
Policy + Capability Discovery
 ↓
Plan v1
 RAG → reasoning → verification
 ↓
RAG execution
 ↓
Evaluation
 → retrieval insufficient
 ↓
Event: RETRIEVAL_INSUFFICIENT
 ↓
Trajectory update
 ↓
Risk / Confidence update
 → confidence reduced
 ↓
Decision
 → current plan not sufficient
 ↓
REPLAN_TRIGGERED
 ↓
Plan v2
 alternate retrieval strategy → verification
 ↓
Execute
 ↓
Evidence sufficient
 ↓
Evaluation + verification pass
 ↓
Answer + trust/limitations
```

If alternate retrieval cannot establish adequate evidence, the terminal decision may be abstention rather than unsupported generation.

---

## 40. Example Flow 4 — Reasoning Uncertainty → Model Escalation

```text
User
 ↓
Fast Path initially
 ↓
Fast model
 ↓
Reasoning evaluation
 → HIGH_REASONING_UNCERTAINTY
 ↓
Event
 ↓
Trajectory/state update
 ↓
Risk increases or confidence decreases
 ↓
Decision Engine
 → current capability insufficient
 ↓
INTERVENTION_TRIGGERED
 → CHANGE_MODEL / INCREASE_REASONING
 ↓
REPLAN_TRIGGERED
 ↓
Plan v2
 stronger reasoning capability → verifier
 ↓
Execute
 ↓
Verify
 ↓
Decision = PASS
 ↓
Improved answer + trust report
```

The runtime changes the strategy itself; it does not merely tell the user to select another model.

---

## 41. Example Flow 5 — High-Risk Agentic Action → Human Approval

```text
User
 ↓
Agentic request
 ↓
Query Intelligence
 → action request
 → high impact
 ↓
Policy
 → external action requires approval
 ↓
Plan
 agent proposes action
 ↓
Action proposal
 ↓
Trajectory / Ledger
 → proposed action
 → permissions
 → destination
 ↓
Action Risk + Confidence
 → high action risk
 ↓
Decision = HUMAN_REVIEW
 ↓
HUMAN_REVIEW_REQUIRED
 ↓
Pause execution
 ↓
Human
 ├── approve
 ├── modify
 ├── reject
 └── escalate
 ↓
ControlPlane records decision
 ↓
If approved:
  authorized execution
       ↓
  post-action verification
       ↓
  final result

If rejected:
  block / abort / replan
```

The agent never obtains authority merely by proposing the action.

---

## 42. Example Flow 6 — Multi-Agent Permission/Data-Lineage Issue

```text
Agent A
  ↓ requests data it cannot directly access
ControlPlane
  ↓ policy / permission boundary
Agent B
  ↓ authorized retrieval
Sensitive data
  ↓
Agent B → Agent A
  ↓
Trajectory lineage update
  ↓
Agent A proposes external transfer
  ↓
Destination + cumulative permissions + data lineage
  ↓
Behavioral / trajectory risk
  ↓
Permission laundering detected
  ↓
Event: PRIVACY_RISK / HIGH_ACTION_RISK
  ↓
Decision
 → block / human / modify / abort
```

The system must evaluate the aggregate trajectory rather than assuming that each individual agent remained compliant in isolation.

---

## 43. Example Flow 7 — Partial Execution Failure

```text
Agent proposal
 ↓
Action 1 authorized
 ↓
Action 1 completed
 ↓
Ledger: COMPLETED
 ↓
Action 2 authorized
 ↓
Action 2 partially executes
 ↓
External system reports partial state
 ↓
Ledger: PARTIALLY_COMPLETED
 ↓
Event: TOOL_FAILURE / PARTIAL_EXECUTION
 ↓
Trajectory update
 ↓
Decision
 ├── retry remaining portion
 ├── compensate/rollback where supported
 ├── human review
 ├── replan
 └── abort / contain
 ↓
Verification of actual external state
 ↓
Final status reflects partial execution if unresolved
```

The system must never convert a partial external outcome into a fabricated `SUCCESS` state.

---

## 44. Example Flow 8 — Shadow-Mode Decision

```text
Application request
      │
      ├──────────────→ Actual execution continues
      │
      ▼
ControlPlane Shadow Mode
      ↓
Query Intelligence
      ↓
Policy context
      ↓
Risk / confidence evaluation
      ↓
Would-be decision:
      REROUTE + HUMAN_REVIEW
      ↓
Record proposed decision
      ↓
Record evidence / policy / reason
      ↓
Do NOT enforce the proposed route change
      ↓
Actual response remains application-controlled
      ↓
Async comparison:
      shadow recommendation
              vs
      actual outcome
      ↓
Learning / policy tuning / evaluation
```

Shadow Mode is observation and decision simulation, not silent enforcement.

---

## 45. End-to-End Decision Loop

The reusable runtime loop is:

```text
                     ┌───────────────────────────────┐
                     │        CURRENT STATE          │
                     │ plan + trajectory + ledger    │
                     │ evidence + risk + confidence  │
                     │ policy + budgets + permissions│
                     └──────────────┬────────────────┘
                                    │
                                    ▼
                             EXECUTE STEP
                                    │
                                    ▼
                              EMIT EVENT
                                    │
                                    ▼
                            UPDATE STATE
                                    │
                                    ▼
                              EVALUATION
                                    │
                                    ▼
                           RISK / CONFIDENCE
                                    │
                                    ▼
                                DECISION
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
              CONTINUE          INTERVENE          TERMINAL
                 │                  │              / HUMAN
                 │                  │                  │
                 │                  ▼                  │
                 │                REPLAN               │
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ▼
                               VERIFICATION
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                  PASS        LIMITATIONS        FAIL
                    │               │               │
                    └───────┬───────┘               │
                            ▼                       │
                           OUTPUT ←─────────────────┘
```

The loop terminates only when the ControlPlane reaches a valid terminal state.

---

## 46. Terminal States

A request should end in an explicit status rather than an ambiguous generic completion.

Conceptual terminal outcomes include:

```text
COMPLETED
COMPLETED_WITH_LIMITATIONS
ABSTAINED
BLOCKED
ABORTED
HUMAN_REVIEW_PENDING
HUMAN_REVIEW_REJECTED
FAILED_SAFE
PARTIALLY_COMPLETED
```

The exact status vocabulary may be refined by the broader runtime contracts, but the important rule is that terminal state must reflect the actual outcome.

---

## 47. Runtime Anti-Patterns

### 47.1 Static route commitment

```text
Query → classifier → fixed route → answer
```

Forbidden as the canonical model because execution evidence can invalidate the initial route.

### 47.2 MCP as decision authority

```text
Agent → MCP → next route selected by adapter
```

Forbidden. MCP provides capability access.

### 47.3 Event bus as workflow engine

```text
EVENT_TYPE → hard-coded next route
```

Forbidden. Events are observations; ControlPlane decides.

### 47.4 Final-answer-only safety

```text
Agent executes everything
→ inspect final text
```

Insufficient for agentic trajectories because data access, permissions, tool calls, and cumulative actions matter.

### 47.5 Unbounded self-healing

```text
failure → retry → retry → retry → ...
```

Forbidden. All intervention is bounded.

### 47.6 Silent fallback

A capability or provider must not silently change route/model/resource in a way that bypasses ControlPlane policy or prevents the route change from being observable.

### 47.7 Fake rollback

The runtime must not claim an external action was undone unless the external system confirms it.

### 47.8 Unsupported answer after evidence failure

If evidence is insufficient, the ControlPlane must recover, escalate, or abstain rather than force a confident-looking unsupported answer.

---

## 48. Runtime Invariants

The following rules must always hold.

1. **ControlPlane is the decision authority.** No capability, model, agent, evaluator, or MCP adapter may silently become the system's routing or policy brain.

2. **Every request is traceable.** Request, trace, and—when applicable—trajectory identity must remain attached to runtime state, events, decisions, and terminal outcomes.

3. **The initial plan is provisional.** New evidence may invalidate it, and the ControlPlane must be able to create a new plan version.

4. **Plan history is immutable.** Replanning creates a new plan version; it must not silently rewrite historical execution facts.

5. **Events are observations, not hidden commands.** The Event Bus communicates what happened; ControlPlane decides what happens next.

6. **Important state changes are explicit.** Consequential failures, risk changes, interventions, replans, human decisions, and verification outcomes must not exist only in informal logs.

7. **Execution is dependency-aware.** Sequential dependencies must be honored, and parallelism must be explicitly justified by the execution plan.

8. **Parallelism is not default fan-out.** ControlPlane should select the smallest useful set of independent capabilities consistent with policy, latency, cost, and risk.

9. **MCP is a capability fabric.** MCP may expose models, data, retrieval, verification, and tools, but it does not own ControlPlane policy or routing authority.

10. **Trajectory state matters.** For multi-step, stateful, tool-using, and agentic workflows, current decisions must account for prior execution, cumulative permissions, cumulative data exposure, cumulative action impact, and new evidence.

11. **The Execution Ledger is append-only for consequential facts.** Historical authorization, action, destination, intervention, and human-override facts must not be silently mutated.

12. **Permission and data lineage must survive composition.** A downstream agent cannot gain effective authority merely because another agent can access data or a capability.

13. **Risk and confidence are separate.** Neither may be used as a hidden substitute for the other, and heuristic confidence must not be presented as calibrated probability without evidence.

14. **High confidence does not make high-risk actions automatically safe.** Policy remains authoritative.

15. **Behavioral drift is a governance signal.** Drift may trigger reassessment, but it must not silently become an unconditional block unless policy says so.

16. **Self-healing is bounded.** No unbounded retry loop is permitted. Intervention must respect policy, evidence, risk thresholds, retry limits, cost, and latency budgets.

17. **Failures preserve diagnosis.** Known failure classes must remain distinguishable so that recovery can be appropriate and auditable.

18. **No unauthorized external action occurs.** Agent or model proposals require ControlPlane authorization before consequential execution.

19. **Partial execution remains visible.** A partially completed or externally persisted action must never be represented as clean success without confirmation.

20. **Rollback is never assumed.** A rollback or compensation is successful only when the relevant external system confirms it.

21. **Human review is an explicit state.** Required approval cannot be implied by timeout, absence of response, or model confidence.

22. **Graceful degradation is policy-bounded.** Loss of a verifier, provider, retrieval source, tool, or telemetry path must not cause an unsafe fail-open behavior.

23. **Abstention is valid.** When trustworthy, authorized completion cannot be established, ControlPlane may abstain rather than fabricate certainty or execute an unsafe action.

24. **Verification failures are actionable.** A failed verification must feed a ControlPlane decision; it cannot be silently ignored.

25. **Output is the best trustworthy permitted result.** The system should attempt recovery and improvement before returning a preventable weak result, while preserving safe abstention where recovery is not justified.

26. **Trust is evidence-backed.** The trust report must be traceable to evaluation, verification, source/evidence state, and relevant limitations.

27. **Shadow and Enforcement are distinguishable.** Shadow-mode proposals must never be represented as executed interventions; enforcement decisions must be explicit in runtime state and telemetry.

28. **Synchronous work is bounded.** Non-critical analytics, dashboard aggregation, historical analysis, and learning should not unnecessarily block the user-critical path.

29. **Learning does not rewrite history.** Future improvements may use past executions, feedback, interventions, and outcomes, but historical runtime facts remain reconstructable.

30. **The runtime must explain consequential decisions.** For any material intervention, replan, escalation, block, abstention, or human review, the system must retain enough decision context to answer what happened, why it happened, what evidence supported it, and what changed.

31. **No route-to-route bypass exists outside ControlPlane.** Capability composition may be flexible, but consequential route changes always return to ControlPlane authority.

32. **The runtime must terminate explicitly.** Every request ends in a meaningful terminal state or an explicit pending-human state; it must not disappear into an ambiguous process state.

---

## 49. Relationship to Adjacent Architecture Contracts

This document defines the runtime lifecycle and should be read alongside:

```text
PRODUCT_THESIS.md
AGENTS.md
docs/ARCHITECTURE.md
docs/ARCHITECTURE/TRAJECTORY_AND_LEDGER.md
docs/ARCHITECTURE/EVENT_MODEL.md
docs/ARCHITECTURE/FAILURE_AND_RECOVERY.md
docs/ARCHITECTURE/SCALE_ARCHITECTURE.md
docs/PROJECT_STATE/CURRENT_STATE.md
```

Those contracts own their respective detail. This document owns the **canonical ordering and control-loop semantics of a single request**.

Where an implementation detail is not established by those contracts, this runtime specification intentionally leaves it open rather than inventing it.
