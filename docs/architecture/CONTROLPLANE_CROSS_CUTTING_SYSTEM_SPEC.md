# ControlPlane.ai — Cross-Cutting System & Operational Specification

**Status:** Supporting implementation contract

**Scope:** Competition Prototype / R2

**Purpose:** Document the cross-cutting system details that are required to turn the existing ControlPlane architecture and component contracts into one coherent implementation, without creating a competing architecture or silently selecting algorithms that belong in the component specifications.

> **This document does not replace the Master Specification, High-Level Architecture, Runtime Flow, Event Model, Trajectory/Ledger, Failure/Recovery, Scale Architecture, or component implementation contracts. It fills cross-cutting operational gaps between them.**

---

# 0. Source-of-Truth Boundary

The current Master Specification defines the authoritative order of the existing documents. This document is subordinate to that hierarchy and must not override it.

Use this document for questions such as:

- How should the services/configuration fit together operationally?
- What common interfaces must every capability obey?
- How are request IDs, trace IDs, plan versions, and correlation IDs propagated?
- What are the common API/error/configuration conventions?
- What must be tested before a component is considered integrated?
- How should secrets, environment variables, health checks, migrations, and startup/shutdown behave?
- What reproducibility and experiment metadata must be preserved?
- What operational boundaries remain intentionally unresolved?

If a conflict appears, follow the Master Specification source order and the more authoritative component contract.

---

# 1. System-Wide Contract Inventory

The implementation is composed of these contract families:

```text
PRODUCT
  → why the system exists and what it must achieve

ARCHITECTURE
  → what components exist and who owns decisions

RUNTIME
  → how one request moves through the system

EVENTS
  → how components communicate observations and state changes

TRAJECTORY / LEDGER
  → what execution history and consequential facts are retained

FAILURE / RECOVERY
  → how failures become bounded recovery decisions

SCALE
  → how the same intelligence loop operates under the competition workload

COMPONENT CONTRACTS
  → routing, retrieval, evaluation, intervention

DATA / STORAGE
  → PostgreSQL, Qdrant, Redis ownership and schemas

OPERATIONS
  → configuration, security, startup, health, testing, reproducibility
```

The last category is the focus of this document.

---

# 2. Common Identity and Correlation Model

Every request and consequential execution step must be traceable across ControlPlane components.

## 2.1 Required identifiers

At minimum, support:

```text
request_id
trace_id
trajectory_id
session_id            nullable
application_id
policy_id             nullable
plan_id
plan_version
step_id
node_id               where graph nodes are distinct
capability_id
model_id              where a model is invoked
route_id               where a route abstraction exists
operation_id           for individual model/tool/retrieval operations
parent_operation_id   for nested operations
 event_id              for emitted events
 decision_id           for ControlPlane decisions
 intervention_id       for interventions
```

## 2.2 Correlation rules

All model, retrieval, tool, evaluation, intervention, and replan records must be linkable back to:

```text
request_id
trace_id
trajectory_id
plan_version
step_id
```

Nested work must preserve causal relationships rather than creating disconnected logs.

## 2.3 No identifier reuse

Identifiers must not be reused across independent requests or trajectories.

---

# 3. Common Request Lifecycle Metadata

At request admission, ControlPlane should establish:

```text
request_id
trace_id
session/application context
policy context
budget context
request timestamp
source/client
```

At completion, record:

```text
final_status
final trust state
final verification state
latency
estimated cost
model/tool/retrieval counts
intervention count
replan count
human-review outcome if applicable
```

The runtime remains the canonical source for which fields are decision-critical versus asynchronous.

---

# 4. Capability Interface Contract

Every capability exposed to ControlPlane should conform to a common logical contract regardless of whether it is implemented directly, through an internal service, or through MCP.

## 4.1 Capability descriptor

```text
capability_id
capability_type
version
supported_tasks
input_schema
output_schema
latency_class
cost_class
risk_class
authorization_requirements
supports_parallel
availability_state
health_state
provider/model metadata where applicable
```

## 4.2 Capability invocation

A capability invocation should conceptually contain:

```text
request_id
trace_id
trajectory_id
plan_id
plan_version
step_id
capability_id
input_reference
policy_context
budget_context
```

The result should provide:

```text
status
result reference / normalized result
latency
usage metadata
warnings
error code if failed
evidence references where applicable
```

## 4.3 Capability rule

A capability reports what happened.

It does **not** decide which successor route should run.

That interpretation remains with ControlPlane.

---

# 5. API Contract

The prototype should expose a small number of stable API boundaries rather than many internal endpoints.

## 5.1 Core request API

Conceptually:

```text
POST /v1/requests
```

Accept:

```text
query
application context
session context
optional user context
policy context if authorized
execution preferences if supported
```

Return:

```text
request_id
trace_id
status
answer when completed synchronously
trust report
verification status
evidence references
limitations
```

The exact external API schema remains an implementation decision and must not contradict the current database/schema contracts.

## 5.2 Request status

For asynchronous or long-running workflows, provide a status/read path conceptually equivalent to:

```text
GET /v1/requests/{request_id}
```

It should expose sanitized execution status, not private model chain-of-thought.

## 5.3 Trace/read interface

The dashboard and internal operators need a structured query for:

```text
request
trajectory
plan versions
events
evaluations
decisions
interventions
ledger facts
final result
```

Do not expose unrestricted internal database access through the user-facing API.

---

# 6. API Response Status Model

Use explicit terminal and non-terminal statuses.

```text
RECEIVED
RUNNING
WAITING_FOR_HUMAN
WAITING_FOR_DEPENDENCY
REPLANNING
VERIFYING
COMPLETED
COMPLETED_WITH_LIMITATIONS
REPAIRED
ESCALATED
ABSTAINED
BLOCKED
FAILED
```

Status transitions must be validated by the runtime state machine.

Do not allow arbitrary components to set terminal status independently.

---

# 7. Error Model

Errors must distinguish between:

```text
CLIENT_ERROR
POLICY_ERROR
VALIDATION_ERROR
AUTHORIZATION_ERROR
CAPABILITY_ERROR
DEPENDENCY_ERROR
MODEL_ERROR
RETRIEVAL_ERROR
DATABASE_ERROR
TIMEOUT
BUDGET_EXCEEDED
RATE_LIMITED
INTERNAL_ERROR
```

Each error should include:

```text
error_code
human-safe message
request_id
trace_id
retryable flag
source component
```

Do not expose:

- provider secrets
- credentials
- raw internal stack traces
- hidden prompts
- private chain-of-thought
- unnecessary sensitive data

---

# 8. Retry and Idempotency Rules

Retries must be governed by the Failure/Recovery contract and never occur indefinitely.

## 8.1 Retryable candidates

Potentially retry:

```text
transient network failures
provider temporary failures
queue delivery failures
idempotent retrieval failures
```

Potentially non-retryable:

```text
policy denial
invalid request
insufficient authorization
known unsupported capability
insufficient evidence
unsafe action
```

## 8.2 Idempotency

Operations that can create external side effects must have idempotency protection where the target system permits it.

A replan must never accidentally duplicate:

```text
financial transfer
email send
CRM mutation
database write
external action
```

because of a retry.

---

# 9. Configuration Model

Do not hard-code operational configuration in source code.

Configuration categories:

```text
application
model registry
provider endpoints
routing policy
risk thresholds
verification policy
budgets
retry limits
replan limits
cache TTLs
event settings
logging levels
feature flags
shadow/enforcement mode
```

## 9.1 Environment variables

Secrets and environment-specific values should come from environment/configuration mechanisms rather than source code.

Examples:

```text
DATABASE_URL
REDIS_URL
QDRANT_URL
MODEL_PROVIDER_KEYS
MCP_ENDPOINTS
APPLICATION_ENV
LOG_LEVEL
```

Do not commit real credentials.

## 9.2 Configuration precedence

Use a documented order such as:

```text
safe application defaults
→ environment configuration
→ deployment configuration
→ policy/config registry
```

Do not let a request arbitrarily override protected policy or infrastructure configuration.

---

# 10. Secrets and Credential Handling

Secrets must:

```text
never be committed
never appear in logs
never be emitted in events
never be stored in ordinary trajectory text
never be included in model prompts unless explicitly required and authorized
```

Tool credentials should be resolved as late as practical and only for the capability that requires them.

The event model already requires security-sensitive events to avoid raw credentials and unnecessary PII. This operational contract extends that rule to configuration and debugging.

---

# 11. Authentication and Authorization Boundary

The API/Gateway establishes identity and application context.

ControlPlane then uses:

```text
application_id
user/session context
role/permission context
policy_id
capability authorization requirements
```

Authorization must be checked before consequential tool execution.

Do not infer authorization merely from:

```text
LLM confidence
query intent
user phrasing
model output
```

A model can propose an action; it cannot grant itself permission.

---

# 12. Policy Configuration Contract

Policies should be represented as explicit configuration rather than scattered conditionals.

Policy dimensions may include:

```text
allowed capabilities
restricted capabilities
risk thresholds
verification requirements
human approval requirements
data-access rules
external-destination rules
budget limits
shadow/enforcement mode
retention requirements
```

Policy is evaluated in context of:

```text
application
user/role
query
trajectory
action
capability
```

The exact policy language/engine remains replaceable unless a concrete implementation decision already exists.

---

# 13. Data Freshness and Source Authority

Every data capability should expose enough metadata to distinguish:

```text
authoritative source
retrieval index
cached result
stale result
external source
synthetic demo source
```

For enterprise facts:

```text
authoritative relational/data source
        ↓
semantic/retrieval index when needed
```

Qdrant is an index, not the source of truth.

Cached results must not silently replace authoritative data when freshness matters.

---

# 14. Data Ingestion Contract

The RAG subsystem needs a reproducible ingestion pipeline.

Conceptually:

```text
source files
 ↓
validation
 ↓
parsing/extraction
 ↓
normalization
 ↓
chunking
 ↓
metadata assignment
 ↓
embedding
 ↓
Qdrant indexing
 ↓
ingestion report
```

Each document/chunk should preserve:

```text
document_id
chunk_id
source
version
content hash
metadata
embedding model/version
ingestion timestamp
```

An ingestion rerun must be able to identify which source/version produced an indexed object.

---

# 15. Model Provider Adapter Contract

Provider-specific details must stay behind adapters.

Conceptually:

```text
ModelProvider
  ├── Local Qwen3 1.3B
  ├── Local Qwen3 4B
  └── Grok API
```

The ControlPlane should call a normalized interface:

```text
generate()
stream()
health()
capabilities()
usage()
```

The adapter returns normalized:

```text
text/result
usage
latency
provider/model id
finish status
error
```

The current model decision record defines the answer-model roles and deliberately keeps provider/model choice under ControlPlane abstraction. Do not hard-code providers into route logic.

---

# 16. Evaluation Adapter Contract

Every evaluator must expose a normalized output.

```text
EvaluationResult
```

Conceptually:

```text
evaluator_id
evaluator_version
scope
score/confidence where applicable
labels
issues
evidence_refs
reason_code
limitations
```

Examples:

```text
quality
factuality
grounding
reasoning
safety
privacy
bias
action_risk
drift
```

Evaluators produce observations. They do not directly mutate the execution graph.

---

# 17. Human Review Contract

Human review is a first-class state, not an error workaround.

A review request should contain:

```text
review_id
request_id
trajectory_id
decision context
risk summary
relevant evidence
proposed action
policy basis
reason for escalation
expiry/deadline if applicable
```

The UI should permit only authorized decisions appropriate to the review context.

Record:

```text
reviewer identity
review timestamp
decision
optional structured reason
```

Do not store private reviewer commentary unless explicitly required.

---

# 18. Shadow Mode Contract

Shadow Mode means:

```text
ControlPlane evaluates
        ↓
records what it would do
        ↓
AI/application behavior remains unchanged
```

Shadow decisions must be distinguishable from enforced decisions in:

```text
decision history
events
dashboard
metrics
```

Never present a shadow decision as an actual intervention.

---

# 19. Feature Flags and Rollout

Use feature flags for risky/new control behaviors.

Potential flags:

```text
enable_dynamic_replanning
enable_behavioral_drift
enable_learned_router
enable_shadow_mode
enable_graceful_degradation
enable_human_review
enable_model_escalation
enable_advanced_rag_evaluator
```

Flags should be:

```text
explicit
versioned
auditable
safe by default
```

Do not hide architectural behavior behind undocumented environment toggles.

---

# 20. Health Checks

Every runtime dependency should expose a basic health/readiness state.

At minimum:

```text
ControlPlane API
PostgreSQL
Redis
Qdrant
model providers
MCP capability groups
```

Distinguish:

```text
process alive
service ready
capability usable
```

A live process is not necessarily a usable dependency.

---

# 21. Startup and Shutdown

Startup should validate:

```text
configuration
required environment variables
database connectivity
schema version
cache/event connectivity
vector-store connectivity
required capability registration
model-provider configuration
```

Graceful shutdown should:

```text
stop accepting new work
finish/cancel bounded in-flight work
persist required terminal state
flush critical events
close connections
```

Do not terminate in-flight high-impact actions without explicit recovery semantics.

---

# 22. Database Migration Contract

Schema changes must be versioned.

Rules:

```text
never silently mutate production/demo schema
use migration files
record migration version
prefer backward-compatible changes
```

A migration should be reversible only when safely possible. Do not claim rollback when a schema/data migration is destructive.

---

# 23. Event Consumer Contract

Every event consumer should define:

```text
consumer name
subscription/filter
expected event versions
idempotency behavior
retry behavior
dead-letter behavior
side effects
metrics
```

Consumers must tolerate duplicate delivery where the transport semantics allow at-least-once delivery.

Consumers should not assume event order unless the event contract explicitly guarantees the ordering scope.

---

# 24. Observability Contract

Three layers should remain distinguishable:

```text
Logs
= diagnostic text/details

Metrics
= numerical aggregates

Traces / Events
= execution structure and causality
```

At minimum collect:

```text
request count
latency p50/p95/p99 when measured
error rate
model calls
retrieval calls
tool calls
replan count
intervention count
human-review count
abstention rate
blocked rate
estimated cost
event rate
consumer lag
retry count
dead-letter count
```

No unmeasured performance number should be presented as a fact.

---

# 25. Logging Rules

Logs should be structured and correlated.

Every meaningful log should include, where available:

```text
request_id
trace_id
trajectory_id
component
operation
severity
timestamp
```

Never log:

```text
API keys
passwords
raw credentials
private chain-of-thought
unnecessary PII
full sensitive documents
```

Log references/identifiers instead where practical.

---

# 26. Audit vs Debug Data

Not all observability data is equal.

Distinguish:

```text
Operational telemetry
Audit/ledger facts
Debug logs
Evaluation artifacts
Training/learning data
```

Do not use debug logs as the audit source of truth.

Do not automatically promote evaluation/debug data into training data without provenance.

---

# 27. Data Retention and Deletion Boundary

Retention is an implementation policy that must be explicit before production use.

At minimum distinguish:

```text
live execution state
trajectory history
execution ledger
raw prompts/responses
retrieval metadata
metrics
aggregates
training/evaluation artifacts
```

Do not assume all data should be retained indefinitely.

Define application-specific retention later where the competition environment does not require it.

---

# 28. Privacy and Data Minimization

The system should prefer:

```text
references over duplicated sensitive payloads
structured metadata over raw secrets
minimal necessary context
field-level filtering
redaction before persistence when policy requires
```

When a sensitive value is needed for the active operation, access it only within the relevant capability boundary.

---

# 29. Security Boundary for MCP

MCP does not receive unrestricted authority merely because it exposes a capability.

Before consequential invocation:

```text
ControlPlane policy
→ authorization
→ action risk
→ budget
→ capability invocation
```

MCP server implementations must not secretly bypass the normal trajectory/event/ledger path.

If an MCP capability performs a consequential side effect, it must emit sufficient execution metadata for the ledger and trace system.

---

# 30. External Side-Effect Contract

External actions should be classified:

```text
READ_ONLY
REVERSIBLE_WRITE
IRREVERSIBLE_WRITE
HIGH_IMPACT_ACTION
```

Higher-impact classes may require:

```text
stronger verification
explicit authorization
human approval
idempotency
post-action verification
```

The classification must be policy-driven.

---

# 31. Parallelism Contract

Parallel execution is allowed only when the planner establishes that tasks are independent enough to run concurrently.

Each parallel branch must still maintain:

```text
shared trace/trajectory identity
branch identity
causal relationship
result aggregation
failure semantics
budget accounting
```

One failed branch must not automatically erase successful independent branches unless the execution contract says the aggregate result is invalid.

---

# 32. Streaming Contract

If streaming output is implemented, the system must distinguish:

```text
provisional tokens/events
final verified response
```

Do not stream a response in a workflow where required verification has not yet completed if the product contract requires verification before release.

For high-risk actions, the system should not treat streamed model text as authorization.

---

# 33. Concurrency and Budget Accounting

Budgets are per execution unless explicitly configured otherwise.

Track:

```text
model calls
retrieval calls
tool calls
parallel branches
replans
latency
cost
```

Budget checks should be deterministic and auditable.

When a budget is exhausted, move to a valid bounded state:

```text
ABSTAIN
ESCALATE
HUMAN_REVIEW
BLOCK
BEST_VERIFIED_RESULT
```

according to policy.

---

# 34. Reproducibility and Experiment Metadata

Every benchmark/algorithm experiment should record:

```text
experiment_id
algorithm/version
model/provider/version
prompt/version where applicable
dataset/version
configuration
seed where applicable
temperature / sampling settings where applicable
hardware/runtime information
metrics
result artifact
```

The same experiment should be rerunnable from the recorded inputs where practical.

---

# 35. Evaluation Protocol Contract

Do not report an improvement without a baseline.

For every intelligent component:

```text
Baseline
→ candidate algorithm
→ identical evaluation set
→ metrics
→ statistical/qualitative comparison where appropriate
→ decision
```

The evaluation set must be separated from data used to tune the method.

Protect the challenge/test set from iterative tuning.

---

# 36. Component-Level Test Pyramid

Every component should have:

```text
Unit Tests
 ↓
Contract Tests
 ↓
Integration Tests
 ↓
Scenario Tests
 ↓
End-to-End Tests
```

## Unit tests

Test deterministic logic independently.

## Contract tests

Verify interfaces between:

```text
ControlPlane ↔ capability
ControlPlane ↔ evaluator
ControlPlane ↔ event system
ControlPlane ↔ storage
```

## Integration tests

Verify real PostgreSQL/Qdrant/Redis/MCP paths in the test environment.

## Scenario tests

Use canonical ControlPlane scenarios.

## End-to-end tests

Validate complete request → answer/action → trust/audit flow.

---

# 37. Required Scenario Test Matrix

At minimum maintain automated or repeatable tests for:

```text
1. Simple factual → fast model
2. Enterprise SQL → SQL capability
3. RAG sufficient → answer
4. RAG insufficient → replan
5. Model reasoning uncertainty → escalation
6. Model/provider failure → fallback
7. High-risk action → human/block
8. PII detection → policy intervention
9. Permission/data lineage anomaly → intervention
10. Multi-agent composition risk → intervention
11. Partial external action → explicit partial state
12. Shadow mode → no enforcement
13. Budget exhaustion → bounded terminal state
14. Event duplication → idempotent handling
15. Qdrant unavailable → controlled degradation
16. Redis unavailable → controlled degradation where safe
17. PostgreSQL unavailable → fail safely
```

---

# 38. Definition of Integration Complete

A component is not integrated merely because its function runs.

It is integrated only when:

```text
[ ] interface defined
[ ] configuration defined
[ ] validation defined
[ ] trace identity propagated
[ ] errors normalized
[ ] timeout/retry semantics defined
[ ] event behavior defined
[ ] persistent state behavior defined
[ ] observability added
[ ] security boundary defined
[ ] tests added
[ ] failure behavior tested
[ ] documentation updated
```

For intelligent components additionally:

```text
[ ] algorithm documented
[ ] baseline documented
[ ] dataset/version documented
[ ] experiment recorded
[ ] metrics recorded
[ ] limitations recorded
```

---

# 39. Versioning Rules

Version separately where semantics can evolve independently:

```text
API version
capability version
event version
plan version
policy version
model version
evaluator version
algorithm version
dataset version
schema/migration version
```

A stored execution record must be interpretable against the versions active when it was produced.

---

# 40. Compatibility Rules

Prefer additive changes.

Breaking changes require explicit versioning or migration.

Examples of breaking changes:

```text
changing event meaning
changing required field semantics
changing capability output contract
changing terminal-status semantics
changing authorization meaning
```

Do not silently reinterpret historical data.

---

# 41. Local Development Environment Contract

The prototype should be runnable through a documented local setup.

Conceptually:

```text
application
PostgreSQL
Qdrant
Redis
MCP capability servers
model adapters
```

The repository should provide:

```text
example environment configuration
startup instructions
migration command
seed-data command
data-ingestion command
test command
health-check command
```

Never commit real secrets.

---

# 42. Seed and Reset Contract

Provide deterministic ways to:

```text
seed synthetic enterprise data
seed documents
build/rebuild Qdrant collections
seed evaluation fixtures
reset local development state
```

Reset operations must not accidentally affect production resources.

---

# 43. Demo Mode

The competition demo should have a controlled environment.

Demo mode may provide:

```text
fixed synthetic dataset
fixed scenario IDs
stable model configuration
predictable external tools
safe simulated side effects
```

The demo should still execute the real ControlPlane control loop rather than hard-coding the final answer.

Avoid scenario-specific logic such as:

```text
if query == "demo question":
    return prewritten answer
```

unless it is explicitly part of a test fixture outside the product path.

---

# 44. Production Evolution Boundary

The prototype is not required to solve every production concern.

Future production concerns may include:

```text
multi-region deployment
stronger secret management
advanced IAM integration
formal compliance workflows
stronger immutable audit storage
advanced autoscaling
provider failover policies
multi-tenant isolation
formal disaster recovery
advanced retention/legal hold
```

These should be documented as future evolution, not falsely claimed as implemented.

---

# 45. Known Unresolved Decisions

Unless an existing concrete contract has already decided them, the following remain open:

```text
exact API framework/auth implementation
exact event transport selection
exact metrics backend
dashboard framework
secret-management system for production
production IAM integration
production retention/legal-hold policy
formal backup/disaster-recovery design
exact burst target
final p95/p99 latency targets
provider-specific concurrency limits
final learned routing model
final learned evaluator models
final intervention-learning method
```

Do not close these decisions by assumption merely to make the documentation look complete.

---

# 46. What This Document Intentionally Does NOT Decide

This document does not select:

- the final query-classification algorithm
- the final risk model
- the final routing algorithm
- the final RAG algorithm
- the final hallucination detector
- the final LLM judge
- the final behavioral-drift algorithm
- the final intervention-learning method
- the final replanner model
- the final trust/calibration method

Those decisions belong to the relevant component specifications and algorithm documents after research and experiments.

---

# 47. Operational Completion Checklist

```text
[ ] Every request has correlation IDs
[ ] Every consequential action is attributable
[ ] Capability contracts are normalized
[ ] API status/error model is explicit
[ ] Retry/idempotency rules exist
[ ] Configuration is externalized
[ ] Secrets are protected
[ ] Authorization precedes consequential actions
[ ] Policy is explicit
[ ] Data freshness/source authority is represented
[ ] Ingestion is reproducible
[ ] Model providers are abstracted
[ ] Evaluators return normalized observations
[ ] Human review is auditable
[ ] Shadow mode is distinguishable from enforcement
[ ] Feature flags are documented
[ ] Health/readiness checks exist
[ ] Startup/shutdown behavior is defined
[ ] Database migrations are versioned
[ ] Event consumers define idempotency/retry behavior
[ ] Logs/metrics/traces are correlated
[ ] Audit/debug/training data are separated
[ ] Retention boundaries are explicit
[ ] MCP capability calls preserve governance metadata
[ ] External side effects are classified
[ ] Parallel branches preserve correlation/budget accounting
[ ] Streaming does not bypass required verification
[ ] Experiment metadata is recorded
[ ] Baseline comparisons exist
[ ] Scenario tests exist
[ ] Integration completion criteria are enforced
[ ] Versioning rules are followed
[ ] Local setup is reproducible
[ ] Seed/reset operations are safe
[ ] Demo mode remains a real execution path
[ ] Unresolved production decisions remain explicitly unresolved
```

---

# 48. Final Rule

This document exists to close the **cross-cutting operational gaps** between the architecture contracts.

Do not turn it into a second architecture brain.

The final system remains:

```text
PRODUCT THESIS
      ↓
MASTER ARCHITECTURE
      ↓
RUNTIME + EVENTS + TRAJECTORY + FAILURE + SCALE
      ↓
COMPONENT IMPLEMENTATION CONTRACTS
      ↓
DATA/STORAGE/MODEL DECISIONS
      ↓
THIS CROSS-CUTTING OPERATIONAL CONTRACT
      ↓
ALGORITHMS + EXPERIMENTS
      ↓
IMPLEMENTATION
```

The implementation must preserve a single principle:

> **Every important action must be attributable, every important decision must be explainable through structured evidence, every recovery must be bounded, and every intelligent component must remain replaceable behind a stable contract.**
