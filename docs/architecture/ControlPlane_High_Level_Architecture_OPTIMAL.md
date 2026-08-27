# ControlPlane.ai — High-Level Architecture
## Research-Aligned, Scale-Aware, Dynamic AI Control Plane

**Status:** Architecture Specification  
**Scope:** Competition Prototype / R2  
**Primary design objective:** Build the smallest architecture that demonstrates the strongest control-plane ideas identified through the current research, while remaining implementable, observable, scalable to the stated workload, and open to future research algorithms.

---

# 1. Architectural Thesis

ControlPlane should not be designed as a system that merely checks individual LLM messages.

The stronger architectural abstraction is:

> **ControlPlane governs the execution trajectory of an AI workflow.**

A trajectory includes:

```text
Query
+
Context
+
Data accessed
+
Permissions
+
Models
+
Retrieval
+
Tools
+
Actions
+
Intermediate state
+
Evaluations
+
Interventions
+
Final outcome
```

This distinction is particularly important for agentic systems, where individually acceptable actions can compose into an unsafe outcome. The research reference identifies trajectory/state/lineage/permissions as the more appropriate unit of risk rather than the message alone. fileciteturn5file0L228-L236

Therefore:

```text
Traditional:
Query → LLM → Response → Checker

ControlPlane:
Query
 ↓
Understand
 ↓
Plan
 ↓
Execute
 ↓
Observe trajectory
 ↓
Evaluate state + response + actions
 ↓
Decide
 ↓
Replan / Intervene
 ↓
Verify
 ↓
Respond / Act
 ↓
Audit + Learn
```

---

# 2. Design Objectives

The architecture must simultaneously optimize for:

1. **Quality** — produce better answers than a fixed baseline when improvement is justified.
2. **Trust** — provide evidence-backed confidence and limitations.
3. **Safety / Responsibility** — control content risk and action risk.
4. **Adaptivity** — change execution when new evidence appears.
5. **Efficiency** — avoid unnecessary expensive models, checks, and tools.
6. **Latency** — preserve fast paths for low-risk use cases.
7. **Recoverability** — self-heal bounded failures.
8. **Auditability** — reconstruct what happened and why.
9. **Scalability** — support the stated 10,000 interactions/week assumption without unnecessary infrastructure.
10. **Research extensibility** — algorithms can be replaced without changing the architecture.

---

# 3. Scale and Reliability Assumption

The competition assumes approximately:

> **10,000 user interactions per week across the specified use cases.**

This is approximately:

```text
~1,430 interactions/day
~60 interactions/hour
~1 interaction/minute
```

These are averages only.

A single interaction may produce multiple internal operations:

```text
Query profiling
→ Risk assessment
→ Routing
→ Retrieval
→ Model call
→ Evaluation
→ Verification
→ Intervention
→ Replanning
→ Tool execution
```

Agentic workflows can create substantially more internal events.

Therefore the architecture must account for:

- burst traffic
- multiple internal events per request
- bounded concurrency
- asynchronous telemetry
- persistent execution state
- horizontal scaling of stateless workers where practical
- timeouts and retries
- failure isolation
- cost and latency budgets

The goal is **not** to build a massive distributed platform for the competition. The goal is to create clean interfaces that can scale without rewriting the intelligence layer.

---

# 4. Core Architectural Model

The complete system consists of:

```text
                    CONTROLPLANE CORE
                           │
       ┌───────────────────┼─────────────────────┐
       │                   │                     │
       ▼                   ▼                     ▼
   INTELLIGENCE          STATE                POLICY
       │                   │                     │
       ▼                   ▼                     ▼
 Query Intelligence   Execution State      Policy Engine
 Planner              Trajectory Store      Risk Rules
 Router               Execution Ledger      Jurisdiction
 Decision Engine      Event History         App Policy
 Replanner
       │
       └───────────────────┬─────────────────────┘
                           │
                 MCP CAPABILITY FABRIC
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
      DATA               MODELS             TOOLS
        │                  │                  │
      SQL/RAG         Fast/Reasoning      CRM/API
      Memory/Web      Specialist          Agent Tools
      Chat DB         Verifiers           Enterprise Apps
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                   EVALUATION LAYER
                           │
                           ▼
                 INTERVENTION ENGINE
                           │
                           ▼
                   FINAL / HUMAN
                           │
                           ▼
                 TRUST + AUDIT + LEARNING
```

---

# 5. Non-Negotiable Architectural Rule

# DO NOT LET MCP BECOME THE BRAIN

MCP is a **capability/interoperability fabric**.

ControlPlane is the authority.

### ControlPlane owns:

- query understanding
- planning
- route selection
- risk
- policy
- trust
- intervention
- replanning
- human escalation
- authorization
- trajectory governance

### MCP provides:

- capability discovery
- standardized invocation
- access to tools/resources/services
- model/data/tool interoperability

The correct relationship is:

```text
Query
 ↓
ControlPlane understands
 ↓
ControlPlane plans
 ↓
ControlPlane decides
 ↓
MCP invokes capability
 ↓
Capability returns result/event
 ↓
ControlPlane updates state
 ↓
ControlPlane decides what happens next
```

Never invert this.

---

# 6. Layer 1 — ControlPlane API / Gateway

## Responsibilities

- authentication
- authorization context
- request identification
- session/context binding
- application identity
- policy selection
- latency/cost budget loading
- rate limiting
- trace creation

Every request receives:

```text
request_id
trace_id
conversation_id
application_id
user/session context
policy_id
```

This boundary must be independent from the internal orchestration logic.

---

# 7. Layer 2 — Query Intelligence

The Query Intelligence Layer produces a **multi-dimensional Query Fingerprint**.

It should not classify a request using only one label.

## Query Fingerprint

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

### Intent

Examples:

```text
informational
factual_lookup
summarization
generation
analytical
reasoning
recommendation
decision_support
action_request
agentic_workflow
personal/conversational
```

### Data Requirements

```text
public_knowledge
enterprise_sql
enterprise_documents
rag
chat_database
memory
web
realtime_api
agent_environment
```

### Complexity

```text
low
medium
high
multi_step
long_context
numerical
coding
planning
multi_agent
```

### Risk Vector

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

The Query Fingerprint is **provisional**.

Later evidence can update it.

---

# 8. Layer 3 — Capability Registry

Before planning, ControlPlane must understand what capabilities are available.

Each capability has a descriptor:

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

Examples:

```text
enterprise_sql
enterprise_rag
chat_history
memory
web_search
fast_model
reasoning_model
coding_model
verifier
crm_tool
email_tool
```

This registry must remain implementation-agnostic.

---

# 9. Layer 4 — Policy Engine

Policy is context-dependent.

The same query can require different treatment depending on:

```text
application
domain
jurisdiction
risk appetite
user role
data sensitivity
actionability
```

The research reference specifically highlights jurisdiction-aware policy as a useful response to changing and geographically different regulatory expectations. fileciteturn5file0L166-L214

The policy engine should therefore support:

```text
application policy
risk policy
tool policy
data policy
verification policy
human-review policy
jurisdiction/rule-pack metadata
cost policy
latency policy
```

Policy must be configuration-driven rather than hard-coded into individual routes.

---

# 10. Layer 5 — Initial Planner

The planner converts the Query Fingerprint, capability registry, and policy into an **Initial Execution Plan**.

Example:

```text
Enterprise SQL
+
Enterprise RAG
        ↓
Driver Analysis
        ↓
Reasoning Model
        ↓
Evidence Verification
```

The plan contains:

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

---

# 11. Layer 6 — Dynamic Execution Graph

The plan is represented as a mutable execution graph.

Support:

```text
add_node
remove_node
skip_node
retry_node
replace_node
switch_model
change_retrieval
increase_reasoning
decrease_reasoning
insert_verifier
pause
resume
human_review
terminate
```

Example:

```text
Initial:

A → B → C
```

After new evidence:

```text
A → B → D → C
```

Parallel:

```text
        ┌→ B ─┐
A ──────┤     ├→ D
        └→ C ─┘
```

The graph is the runtime representation of the current execution strategy.

---

# 12. Layer 7 — Shared Execution State

Every request has an `ExecutionState`.

```text
request_id
trace_id

query
query_profile

current_plan
plan_version

current_step
completed_steps
pending_steps

evidence
risk_state
confidence_state

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
trajectory_state

final_answer
trust_report
final_status
```

The shared state is the basis for runtime decisions.

---

# 13. Layer 8 — Trajectory Store + Execution Ledger

This should be a **first-class subsystem**, not merely logging.

The research identifies trajectory/state/lineage/permissions as critical for agentic risk, and specifically recommends a trajectory store plus execution ledger tracking what the agent touched and did. fileciteturn5file0L391-L395

## Trajectory Store

Records the evolving workflow:

```text
step_1
step_2
step_3
...
```

## Execution Ledger

Records:

```text
data accessed
documents accessed
tools called
permissions used
models used
actions taken
external destinations
state changes
human approvals
interventions
```

This allows ControlPlane to reason about:

> **What has happened so far?**

not merely:

> What did the last response say?

---

# 14. Layer 9 — Event Bus

Components communicate important state transitions as structured events.

```text
Capability
 ↓
Event
 ↓
Event Bus
 ↓
ControlPlane
 ↓
Decision
 ↓
Replan
```

Potential events:

```text
QUERY_RECLASSIFIED
DATA_REQUIRED
DATA_UNAVAILABLE
RETRIEVAL_INSUFFICIENT
EVIDENCE_CONFLICT
HIGH_REASONING_UNCERTAINTY
MODEL_DISAGREEMENT
PERMISSION_ESCALATION
PII_DETECTED
PRIVACY_RISK
BIAS_RISK
SAFETY_RISK
HIGH_ACTION_RISK
BEHAVIORAL_DRIFT_HIGH
TOOL_FAILURE
MODEL_FAILURE
LATENCY_BUDGET_WARNING
COST_BUDGET_WARNING
VERIFICATION_FAILED
HUMAN_REVIEW_REQUIRED
```

Do not use direct route-to-route coupling for re-planning.

---

# 15. Layer 10 — Behavioral State / Drift Monitor

This is a research-derived addition.

Instead of evaluating only static risk, maintain a lightweight **Behavioral Drift Score**.

The research proposes a buildable weighted score based on signals such as tool velocity, data-source deviation, action sensitivity, conversation length, and monetary deviation. fileciteturn5file0L321-L336

Conceptually:

```text
Expected trajectory
        vs
Actual trajectory
        ↓
Behavioral Drift Score
```

Possible signals:

```text
unexpected tool frequency
unexpected data source
unexpected permission use
unexpected external destination
unexpected monetary amount
unexpected conversation length
unexpected action sensitivity
```

This does not need a complex ML model for the prototype.

The score should be:

- configurable
- explainable
- traceable
- bounded
- usable as one signal among several

---

# 16. Layer 11 — Capability / MCP Fabric

MCP can expose:

```text
SQL
RAG
Web
Memory
Chat DB
Models
Verification
Enterprise APIs
Agent Tools
```

Architecture:

```text
ControlPlane
 ↓
MCP Adapter
 ↓
MCP Server
 ↓
Capability
 ↓
Normalized Result
 ↓
ExecutionState / Event Bus
```

MCP is replaceable.

The rest of ControlPlane should use internal capability contracts rather than scattering MCP-specific types throughout the codebase.

---

# 17. Layer 12 — Parallel Capability Execution

Parallelism is dynamic.

If tasks are independent:

```text
                 Query
                   ↓
              ControlPlane
                   ↓
          ┌────────┼────────┐
          ▼        ▼        ▼
        SQL      RAG      Memory
          │        │        │
          └────────┼────────┘
                   ▼
              Evidence Merge
```

If tasks are dependent:

```text
SQL
 ↓
Interpret SQL
 ↓
Reasoning
```

The planner chooses parallel or sequential execution based on:

```text
dependencies
latency
cost
risk
expected information gain
policy
```

---

# 18. Layer 13 — Model Capability Layer

Models are capabilities, not hard-coded application logic.

Potential classes:

```text
fast
balanced
reasoning
coding
long_context
multimodal
private
high_reliability
verifier
```

Maintain observed capability profiles:

```text
task_class
quality
latency
cost
failure_patterns
strengths
weaknesses
```

The routing system eventually learns:

> Which capability has the best expected outcome for this task under the current constraints?

---

# 19. Layer 14 — Data Capability Layer

## SQL

Use for:

- authoritative quantitative information
- structured enterprise data
- deterministic computation

## RAG

Use for:

- enterprise documents
- policies
- reports
- manuals

Return:

```text
sources
chunks
retrieval scores
source metadata
evidence adequacy
freshness
```

## Chat Database

Use for:

- customer support history
- internal discussions
- conversations

## Memory

Use for:

- user preferences
- conversational context

## Web/Search

Use for:

- current external knowledge

When authoritative enterprise data exists, prefer it over LLM memory.

---

# 20. Layer 15 — Agent / Tool Execution

Agentic workflows are governed at the trajectory level.

```text
Agent
 ↓
Plan
 ↓
Proposed Tool Call
 ↓
ControlPlane Policy
 ↓
Risk
 ↓
ALLOW / MODIFY / HUMAN / BLOCK
 ↓
MCP Tool
 ↓
Result
 ↓
Ledger
 ↓
Post-action Verification
```

Never allow a model/agent to bypass ControlPlane authorization.

---

# 21. Layer 16 — Permission and Lineage Control

Track:

```text
who requested
who accessed
what data was accessed
which permission enabled it
where the data went
which agent initiated the action
which other agents participated
```

This addresses trajectory-level failures such as **permission laundering**, where a restricted agent obtains sensitive data through another agent. The research explicitly identifies this as a multi-agent risk. fileciteturn5file0L281-L290

---

# 22. Layer 17 — Evaluation Layer

Evaluation is modular.

Potential evaluators:

```text
Quality
Factuality
Grounding
Reasoning
Safety
Privacy
PII
Bias
Security
Cost
Latency
Action Risk
Consistency
```

Each returns:

```text
score
confidence
issues
evidence
recommended_action
```

No single evaluator should have total authority.

---

# 23. Layer 18 — Defense-in-Depth

The research recommends multiple independent control layers rather than relying on a single checker. fileciteturn5file0L398-L407

Conceptually:

```text
Deterministic Rules
        ↓
Policy Engine
        ↓
Behavioral Drift
        ↓
Evidence / Grounding
        ↓
Model Evaluation
        ↓
Verifier
        ↓
Decision Engine
```

A single model or evaluator must not be able to silently override every other safety signal.

---

# 24. Layer 19 — Risk × Confidence Decision Matrix

The final control decision should consider at least:

```text
Risk
+
Confidence
+
Policy
+
Impact
+
Trajectory
```

A simple initial policy matrix:

```text
                     CONFIDENCE
                HIGH            LOW

LOW RISK        PASS            MONITOR

HIGH RISK       MONITOR/VERIFY  ESCALATE/BLOCK
```

Possible decisions:

```text
PASS
MONITOR
ESCALATE
BLOCK
```

The exact thresholds must be configurable per use case.

This aligns with the research recommendation to avoid a simple binary pass/block mechanism. fileciteturn5file0L391-L400

---

# 25. Layer 20 — Intervention Engine

The Intervention Engine translates control decisions into actions.

Possible interventions:

```text
KEEP
VERIFY
RETRIEVE_MORE
RERANK
CHANGE_MODEL
INCREASE_COMPUTE
DECREASE_COMPUTE
CHANGE_DATA_SOURCE
REGENERATE
REPAIR
REDACT
ASK_CLARIFICATION
HUMAN_REVIEW
ABSTAIN
BLOCK
```

Selection should consider:

```text
expected quality gain
risk reduction
cost
latency
policy
remaining budget
```

---

# 26. Layer 21 — Graceful Degradation

Do not use only:

```text
ALLOW
BLOCK
```

The system can progressively reduce autonomy:

```text
FULL CAPABILITY
      ↓
RESTRICT TO READ-ONLY
      ↓
DISABLE EXTERNAL TOOLS
      ↓
DRAFT ONLY
      ↓
HUMAN APPROVAL
      ↓
BLOCK
```

The research identifies graceful degradation as a practical alternative to binary blocking. fileciteturn5file0L359-L369

This is particularly valuable for agents.

---

# 27. Layer 22 — Partial Execution / Action Transaction State

Agentic systems may fail after partially performing an action.

Therefore track:

```text
PROPOSED
AUTHORIZED
EXECUTING
PARTIALLY_COMPLETED
COMPLETED
COMPENSATION_REQUIRED
ROLLED_BACK
HUMAN_REVIEW
```

The architecture should distinguish:

```text
Can continue safely?
Can compensate?
Must roll back?
Must escalate?
```

A full rollback engine is not required for the competition prototype unless the demo workflow needs it, but the state model must acknowledge partial execution.

---

# 28. Layer 23 — Shadow Mode

A major enterprise adoption feature.

## Shadow mode

ControlPlane observes and evaluates but does not enforce.

```text
AI executes normally
        ↓
ControlPlane evaluates
        ↓
Would have:
- rerouted
- verified
- escalated
- blocked
        ↓
LOG ONLY
```

This lets teams measure:

```text
false positives
false negatives
expected interventions
latency impact
route changes
```

before enforcement.

The research explicitly identifies Shadow Mode as a strong practical mechanism. fileciteturn5file0L345-L357

Modes:

```text
SHADOW
MONITOR
RESTRICTED
HUMAN_APPROVAL
ENFORCE/BLOCK
```

---

# 29. Layer 24 — Best-Answer Objective

ControlPlane should not merely report that a model is wrong.

It should improve the execution when possible:

```text
Weak response
 ↓
Detect problem
 ↓
Intervene
 ↓
Replan
 ↓
Better model/retrieval/tool
 ↓
Verify
 ↓
Improved answer
```

The user should receive:

```text
final answer
+
trust
+
evidence
+
limitations
```

not merely:

```text
"Your model failed."
```

---

# 30. Layer 25 — Trust and Evidence Output

Trust should be evidence-backed.

Example:

```text
TRUST: HIGH

Why:
✓ Evidence supports the primary claims
✓ Authorized enterprise source
✓ Verification passed
✓ No major disagreement

Limitations:
⚠ Q4 data unavailable
```

Low-trust case:

```text
TRUST: LOW

Why:
⚠ Evidence insufficient
⚠ Conflicting sources
⚠ Model disagreement

ControlPlane:
Did not present unsupported information as fact.
```

Do not fabricate precise probabilities without a justified calibration method.

---

# 31. Layer 26 — Abstention

Abstention is a valid final state.

Possible statuses:

```text
ANSWERED
ANSWERED_WITH_LIMITATIONS
REPAIRED
ESCALATED
HUMAN_APPROVED
BLOCKED
ABSTAINED
FAILED
```

Abstention should communicate:

```text
what is missing
what was checked
why confidence is low
what would be required to continue
```

---

# 32. Layer 27 — History / Auditability

Every interaction should have an auditable record.

## Query History

```text
request_id
timestamp
query
query_profile
risk_profile
final_status
```

## Route History

```text
plan_version
from_node
to_node
reason
event
timestamp
```

## Decision History

```text
decision_id
decision
reason
evidence
confidence
policy
cost
latency
outcome
```

## Execution Ledger

```text
data accessed
permissions
tools
models
actions
destinations
interventions
```

## Human Overrides

Record:

```text
who
when
what was overridden
why
```

The research explicitly recommends tamper-resistant, append-only audit behavior for governance. fileciteturn5file0L110-L126

For the prototype, implement immutable/append-only semantics at the application level and document stronger storage hardening as a future production concern if necessary.

---

# 33. Layer 28 — Critical Path vs Async Infrastructure

### User-critical path

```text
Query
→ profiling
→ routing
→ execution
→ required verification
→ intervention/replan
→ final response
```

### Async path

```text
telemetry
history enrichment
dashboard aggregation
benchmarking
offline evaluation
route statistics
learning
```

The dashboard should not unnecessarily block the user response.

---

# 34. Layer 29 — Fast Path vs Deep Path

## Fast Path

```text
low risk
+
high confidence
+
simple task
        ↓
fast capability
+
light checks
```

## Deep Path

```text
high risk
or
low confidence
or
high complexity
or
high-impact action
        ↓
stronger capability
+
evidence
+
multiple controls
+
human if required
```

This directly addresses the research finding that checking everything thoroughly is too slow, while checking too little is too risky. fileciteturn5file0L64-L69

---

# 35. Layer 30 — Failure Isolation and Bounded Recovery

Failures should be explicit:

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

Recovery is bounded by:

```text
max_replans
max_model_calls
max_tool_calls
max_latency
max_cost
policy
risk threshold
```

Never retry indefinitely.

---

# 36. Layer 31 — Scale Architecture

The ControlPlane API/orchestration layer should be horizontally scalable:

```text
                 Load Balancer
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     Worker 1      Worker 2      Worker 3
        │             │             │
        └─────────────┼─────────────┘
                      ▼
             Shared State / Services
```

Potential infrastructure:

```text
API
Workers
Persistent DB
Cache
Event/Queue
Vector DB
Model providers
MCP servers
Telemetry
```

At the competition scale, prefer simple technologies and clean interfaces.

Do not introduce Kafka/Kubernetes merely for appearance.

---

# 37. Layer 32 — Model/Provider Abstraction

Models should be accessed through a provider abstraction.

```text
ModelProvider
    ├── Provider A
    ├── Provider B
    ├── Provider C
    └── Local / Fine-tuned Model
```

This enables:

```text
routing
fallback
benchmarking
A/B testing
cost comparison
latency comparison
```

Provider-specific code must not leak into the central planner.

---

# 38. Layer 33 — Persistent and Observable Execution

Critical state should not live only in process memory.

Persist:

```text
ExecutionState
Trajectory
ExecutionLedger
Plan versions
Events
Evaluations
Interventions
Trust report
Human-review status
```

Trace every important model/tool/retrieval invocation.

Minimum telemetry:

```text
request_id
trace_id
timestamp
capability
model
latency
token usage
estimated cost
status
error
```

---

# 39. Layer 34 — Data and Learning Loop

Every completed execution contributes:

```text
query
profile
plan
trajectory
events
risk
interventions
outcome
feedback
cost
latency
trust
```

This supports future learning of:

```text
query profiling
model routing
risk scoring
intervention selection
model capability profiles
verifier selection
```

The initial prototype does not need to train a sophisticated online learning system.

The architecture should simply preserve the data necessary to build one later.

---

# 40. Layer 35 — Documentation and Experimental Traceability

Every architecture-affecting implementation change must update the relevant project documentation.

At minimum:

```text
PRODUCT_THESIS.md
docs/ARCHITECTURE.md

docs/ARCHITECTURE/
    SCALE_ARCHITECTURE.md
    EVENT_MODEL.md
    RUNTIME_FLOW.md
    FAILURE_AND_RECOVERY.md

docs/PROJECT_STATE/
    CURRENT_STATE.md
    PROGRESS.md
    FUTURE_WORK.md
    DECISIONS.md
```

Algorithms remain independently documented and replaceable.

---

# 41. Core End-to-End Runtime Flow

The final runtime should conceptually be:

```text
                         USER
                           │
                           ▼
                  ┌─────────────────┐
                  │ API / Gateway   │
                  └────────┬────────┘
                           ▼
                 ┌───────────────────┐
                 │ Query Intelligence│
                 └────────┬──────────┘
                          ▼
                  ┌─────────────────┐
                  │ Policy Context  │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ Initial Planner │
                  └────────┬────────┘
                           ▼
                Dynamic Execution Graph
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
            SQL           RAG          Agent
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                  Trajectory + Ledger
                           │
            ┌──────────────┼───────────────┐
            ▼              ▼               ▼
          Risk           Drift          Evidence
            │              │               │
            └──────────────┼───────────────┘
                           ▼
                     Evaluation Layer
                           │
                           ▼
                 Risk × Confidence Matrix
                           │
            ┌──────────────┼───────────────┐
            ▼              ▼               ▼
           PASS          MONITOR       ESCALATE/BLOCK
            │              │               │
            │              ▼               ▼
            │          Intervene         Human
            │              │
            └──────────────┼──────────────┘
                           ▼
                       Replanner
                           │
                      New Execution
                           │
                           ▼
                        Verify
                           │
                           ▼
                 Best Available Answer
                           │
                           ▼
                Trust + Evidence + Limits
                           │
                           ▼
                          USER
                           │
                    Async Learning
```

---

# 42. Canonical Scenarios

The prototype should validate at least these workflows.

## Scenario 1 — Public factual

```text
Query
→ fast model
→ light verification
→ answer
```

## Scenario 2 — Enterprise factual

```text
Query
→ SQL
→ deterministic result
→ explanation
→ evidence
```

## Scenario 3 — Insufficient RAG

```text
Query
→ RAG
→ insufficient evidence
→ event
→ replan
→ alternate retrieval
→ verify
→ answer / abstain
```

## Scenario 4 — Difficult reasoning

```text
Query
→ initial model
→ reasoning uncertainty
→ stronger reasoning
→ verifier
→ answer
```

## Scenario 5 — Agentic high-risk action

```text
Query
→ agent
→ tool proposal
→ trajectory/action risk
→ policy
→ human/block
→ execute if allowed
→ verify
```

## Scenario 6 — Multi-agent composition

```text
Agent A
 ↓
Agent B
 ↓
Sensitive data
 ↓
Unexpected external destination
 ↓
Trajectory / permission-lineage detection
 ↓
Intervention
```

The research recommends one concrete multi-agent demo where the unsafe outcome emerges from composition rather than a single obviously bad message. fileciteturn5file0L391-L407

---

# 43. Prototype Prioritization

## P0 — Build

```text
Query Intelligence
Planner
Execution Graph
Execution State
Trajectory Store
Execution Ledger
Event Bus
Policy Engine
Basic Risk
Risk × Confidence Matrix
Basic Evaluation
Intervention
Replanning
Shadow Mode
Trust/Evidence Output
Dashboard
MCP Capability Fabric
Basic Scale/Telemetry
```

## P1 — Strong additions

```text
Behavioral Drift Score
Permission Lineage
Graceful Degradation
Multi-agent trajectory demo
More robust RAG adequacy
Better model routing
Model capability profiles
```

## P2 — Research/Future

```text
Conformal prediction
Adaptive test-time compute
Learned intervention policies
Advanced online routing
Advanced trajectory risk models
Formal rollback/compensation systems
```

The research specifically recommends leaving conformal prediction, adaptive test-time compute, and chaos engineering outside the R2 core implementation. fileciteturn5file0L381-L387

---

# 44. Trade-offs and Explicit Decisions

## Accuracy vs Latency

Do not run deep verification on every request.

Use:

```text
risk × confidence × impact
```

to allocate compute.

## Safety vs Availability

Prefer graceful degradation, human review, or abstention over unnecessary full blocking when policy permits.

## Centralization vs Modularity

Centralize **decision authority** in ControlPlane, but modularize **capabilities**.

## MCP vs Internal APIs

Use MCP where interoperability helps. Do not force every internal interaction through MCP.

## Event Bus vs Direct Calls

Use events for decoupled observation and replanning triggers. Use direct internal function/service calls when strict sequential dependency is simpler and appropriate.

## Prototype vs Production Scale

Build production-compatible interfaces, not production-level infrastructure complexity.

## Automated Evaluation vs Human Truth

Use automated evaluation to scale, but keep human-validated subsets for calibration and validation.

---

# 45. Definition of Done

The architecture is considered coherent when:

```text
[ ] Query can be profiled
[ ] Initial plan can be generated
[ ] Plan is represented as an execution graph
[ ] State is persistent/traceable
[ ] Trajectory and ledger exist
[ ] Events can trigger replanning
[ ] MCP can expose capabilities without owning decisions
[ ] Parallel execution is supported where useful
[ ] Risk and confidence affect control decisions
[ ] Behavioral drift can be added without redesign
[ ] Multiple independent controls can contribute to a decision
[ ] Intervention can repair or reroute
[ ] Self-healing is bounded
[ ] Shadow Mode is supported
[ ] High-impact actions can require human approval
[ ] Final answer includes trust/evidence/limitations
[ ] Full route history is auditable
[ ] Async observability does not unnecessarily block responses
[ ] 10,000 interactions/week is a documented capacity assumption
[ ] Load testing is possible
[ ] Algorithms can be replaced without changing core contracts
```

---

# 46. Final Architecture Principle

ControlPlane should be understood as:

```text
                   CONTROLPLANE.AI

        UNDERSTAND
             ↓
           PLAN
             ↓
         EXECUTE
             ↓
          OBSERVE
             ↓
         EVALUATE
             ↓
          DECIDE
             ↓
      REPLAN / SELF-HEAL
             ↓
          VERIFY
             ↓
         RESPOND
             ↓
           LEARN
```

with five core architectural ideas:

```text
1. CONTROL THE TRAJECTORY, NOT JUST THE MESSAGE
2. CONTROLPLANE OWNS DECISIONS; MCP PROVIDES CAPABILITIES
3. RISK × CONFIDENCE DETERMINES CONTROL DEPTH
4. SELF-HEALING MUST BE BOUNDED AND AUDITABLE
5. EVERY IMPORTANT DECISION MUST LEAVE A TRACE
```

The product is strongest when it does not merely say:

> **"This AI output is risky."**

It should be able to say, and preferably demonstrate:

> **"This execution has deviated from the expected trajectory; here is the evidence, here is the policy and confidence state, here is the intervention we selected, here is the new execution path, here is the resulting answer, and here is why the result should or should not be trusted."**
