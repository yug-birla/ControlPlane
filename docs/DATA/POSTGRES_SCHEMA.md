# ControlPlane.ai — PostgreSQL Schema Contract

**Status:** Prototype Database Contract  
**Database:** PostgreSQL  
**Purpose:** Define the relational schema for authoritative ControlPlane state, trajectory/ledger data, capability metadata, and synthetic enterprise/evaluation data.

> This document defines logical schema and relationships. Physical partitioning/index tuning can evolve after measurement.

---

# 1. Database Layout

Use one PostgreSQL deployment initially.

Logical databases/schemas:

```text
controlplane
enterprise_demo
evaluation
```

Do not create separate PostgreSQL servers for each domain unless required later.

---

# 2. Naming Rules

Use:

```text
snake_case
plural table names
singular semantic entities in documentation
```

Examples:

```text
query_profiles
execution_states
plan_versions
human_reviews
```

Primary key convention:

```text
id
```

Foreign-key convention:

```text
<entity>_id
```

Timestamps:

```text
created_at
updated_at
started_at
completed_at
```

All persisted timestamps use UTC.

---

# 3. CONTROLPLANE DOMAIN

## 3.1 requests

Purpose: one row per incoming user/application request.

Fields:

```text
id UUID PK
trace_id UUID/UUID-like
session_id UUID nullable
application_id TEXT
user_context_id TEXT nullable
query_text TEXT
status TEXT
policy_id UUID nullable
priority TEXT nullable
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
completed_at TIMESTAMPTZ nullable
```

`query_text` may be redacted/hashed according to application policy.

---

## 3.2 query_profiles

Purpose: store the versioned Query Fingerprint.

Fields:

```text
id UUID PK
request_id UUID FK
version INTEGER
intent TEXT/JSONB
domain TEXT/JSONB
data_requirements JSONB
complexity JSONB
sensitivity JSONB
impact JSONB
actionability JSONB
risk_vector JSONB
confidence JSONB
source TEXT
created_at TIMESTAMPTZ
```

A request may have multiple profiles because the architecture allows reclassification after new evidence.

---

## 3.3 execution_states

Purpose: current authoritative runtime snapshot.

Fields:

```text
trajectory_id UUID PK
request_id UUID FK
current_plan_version_id UUID nullable
current_node_id UUID nullable
status TEXT
risk_state JSONB
confidence_state JSONB
drift_state JSONB
budget_state JSONB
evidence_state JSONB
active_capabilities JSONB
active_tools JSONB
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Do not store the entire event history inside this row.

This is the current state.

---

# 4. PLANNING DOMAIN

## 4.1 plans

```text
id UUID PK
request_id UUID FK
plan_type TEXT
initial_reason JSONB
status TEXT
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

---

## 4.2 plan_versions

Each replan creates a new version.

```text
id UUID PK
plan_id UUID FK
version INTEGER
parent_version_id UUID nullable
trigger_event_id UUID nullable
change_reason JSONB
cost_budget NUMERIC nullable
latency_budget_ms BIGINT nullable
verification_level TEXT
created_at TIMESTAMPTZ
```

Never overwrite an old plan version.

---

## 4.3 execution_nodes

Represents nodes in the execution graph.

```text
id UUID PK
plan_version_id UUID FK
node_key TEXT
capability_id UUID
node_type TEXT
status TEXT
dependency_definition JSONB
parallel_group TEXT nullable
input_contract JSONB
output_contract JSONB
retry_budget INTEGER
timeout_ms BIGINT
created_at TIMESTAMPTZ
started_at TIMESTAMPTZ nullable
completed_at TIMESTAMPTZ nullable
```

Node lifecycle:

```text
PENDING
READY
RUNNING
COMPLETED
FAILED
SKIPPED
CANCELLED
WAITING_HUMAN
```

---

# 5. ROUTING / CAPABILITY DOMAIN

## 5.1 capability_registry

```text
id UUID PK
capability_key TEXT UNIQUE
type TEXT
description TEXT
latency_class TEXT
cost_class TEXT
risk_class TEXT
supports_parallel BOOLEAN
requires_authorization BOOLEAN
input_schema JSONB
output_schema JSONB
availability_status TEXT
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

The architecture requires capability metadata so the planner reasons over capabilities instead of hard-coded implementations. fileciteturn2file2L465-L483

---

## 5.2 model_registry

```text
id UUID PK
model_key TEXT UNIQUE
provider TEXT
display_name TEXT
capabilities JSONB
context_window INTEGER nullable
latency_class TEXT
cost_class TEXT
reasoning_strength TEXT nullable
known_strengths JSONB
known_weaknesses JSONB
availability_status TEXT
version TEXT nullable
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Do not store API keys here.

---

## 5.3 route_registry

```text
id UUID PK
route_key TEXT UNIQUE
route_type TEXT
required_capabilities JSONB
allowed_models JSONB
allowed_data_sources JSONB
risk_level TEXT
verification_level TEXT
cost_class TEXT
latency_class TEXT
supports_parallel BOOLEAN
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

---

# 6. GOVERNANCE DOMAIN

## 6.1 policies

```text
id UUID PK
policy_key TEXT UNIQUE
application_id TEXT nullable
policy_type TEXT
version INTEGER
rules JSONB
risk_thresholds JSONB
allowed_interventions JSONB
human_review_rules JSONB
data_access_rules JSONB
tool_rules JSONB
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Never overwrite an active policy version without preserving history.

---

## 6.2 decisions

Every major ControlPlane decision is persisted.

```text
id UUID PK
request_id UUID FK
trajectory_id UUID FK
plan_version_id UUID nullable
decision_type TEXT
decision TEXT
reason JSONB
risk_snapshot JSONB
confidence_snapshot JSONB
evidence_refs JSONB
policy_id UUID nullable
cost_snapshot JSONB
latency_snapshot JSONB
created_at TIMESTAMPTZ
```

Possible decision values:

```text
PASS
MONITOR
INTERVENE
ESCALATE
ABSTAIN
BLOCK
REPLAN
HUMAN_REVIEW
```

---

## 6.3 interventions

```text
id UUID PK
request_id UUID FK
trajectory_id UUID FK
decision_id UUID FK
intervention_type TEXT
target_node_id UUID nullable
reason JSONB
expected_effect JSONB
actual_effect JSONB nullable
status TEXT
created_at TIMESTAMPTZ
completed_at TIMESTAMPTZ nullable
```

Use the current intervention taxonomy defined by the data workstream:

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

fileciteturn2file7L1430-L1452

---

# 7. EVALUATION DOMAIN

## 7.1 evaluations

```text
id UUID PK
request_id UUID FK
trajectory_id UUID FK
node_id UUID nullable
evaluator_type TEXT
algorithm_version TEXT
score JSONB
confidence JSONB
issues JSONB
evidence_refs JSONB
recommended_action TEXT nullable
created_at TIMESTAMPTZ
```

Potential evaluator types include:

```text
quality
factuality
grounding
reasoning
safety
privacy
pii
bias
security
action_risk
consistency
rag_adequacy
```

The product thesis defines evaluation as modular with structured score/confidence/evidence/issues/recommendation output. fileciteturn2file8L1789-L1825

---

## 7.2 trust_reports

```text
id UUID PK
request_id UUID FK
trajectory_id UUID FK
trust_level TEXT
supporting_signals JSONB
evidence_refs JSONB
limitations JSONB
generated_at TIMESTAMPTZ
```

Do not store arbitrary numeric "trust" without defining what it represents.

---

## 7.3 human_reviews

```text
id UUID PK
request_id UUID FK
trajectory_id UUID FK
review_type TEXT
reviewer_id TEXT
decision TEXT
reason TEXT
overridden_decision_id UUID nullable
created_at TIMESTAMPTZ
```

Possible decisions:

```text
APPROVE
REJECT
MODIFY
ABSTAIN
```

---

# 8. EVENT DOMAIN

## 8.1 event_index

Durable index/summary of runtime events.

```text
id UUID PK
event_type TEXT
event_version TEXT
request_id UUID FK
trace_id TEXT
trajectory_id UUID FK
plan_version_id UUID nullable
node_id UUID nullable
source_type TEXT
source_id TEXT
severity TEXT
observed_at TIMESTAMPTZ
persisted_at TIMESTAMPTZ
causation_id UUID nullable
correlation_id UUID nullable
payload JSONB
schema_version TEXT
```

The Event Model requires events to carry structured identifiers, source, timestamps, version and normalized semantics. fileciteturn2file6L1371-L1404

---

# 9. TRAJECTORY DOMAIN

## 9.1 trajectories

```text
id UUID PK
request_id UUID FK
trajectory_type TEXT
status TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ nullable
current_plan_version_id UUID nullable
final_status TEXT nullable
```

---

## 9.2 trajectory_steps

```text
id UUID PK
trajectory_id UUID FK
sequence_number INTEGER
plan_version_id UUID nullable
node_id UUID nullable
step_type TEXT
actor_type TEXT
actor_id TEXT nullable
input_ref JSONB
output_ref JSONB
status TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ nullable
```

---

# 10. EXECUTION LEDGER

## 10.1 execution_ledger

This is append-only at the application level.

```text
id UUID PK
trajectory_id UUID FK
sequence_number BIGINT
occurred_at TIMESTAMPTZ
actor_type TEXT
actor_id TEXT
action_type TEXT
resource_type TEXT
resource_id TEXT
permission_used TEXT nullable
source TEXT nullable
destination TEXT nullable
authorization_result TEXT nullable
consequence_class TEXT
evidence_refs JSONB
metadata JSONB
```

Examples:

```text
MODEL_INVOKED
DOCUMENT_ACCESSED
DATABASE_READ
TOOL_PROPOSED
TOOL_AUTHORIZED
TOOL_DENIED
TOOL_EXECUTED
EXTERNAL_ACTION
HUMAN_APPROVAL
DATA_TRANSFER
INTERVENTION
```

Do not update old ledger records.

If a correction is required, append a compensating record.

The trajectory contract defines the ledger as an append-only record of consequential execution facts. fileciteturn1file4L16-L30

---

# 11. COST / LATENCY

## 11.1 execution_metrics

```text
id UUID PK
request_id UUID FK
trajectory_id UUID FK
node_id UUID nullable
model_id UUID nullable
tool_id TEXT nullable
input_tokens BIGINT nullable
output_tokens BIGINT nullable
latency_ms BIGINT
estimated_cost NUMERIC nullable
timestamp TIMESTAMPTZ
```

This supports cost/latency-aware intervention and routing.

---

# 12. SYNTHETIC ENTERPRISE DOMAIN

The data workstream explicitly requires a synthetic enterprise environment and forbids use of real confidential data. fileciteturn2file5L1087-L1138

Recommended tables:

```text
employees
customers
products
orders
transactions
revenue
support_tickets
departments
conversations
conversation_messages
```

All synthetic records should have stable IDs.

---

# 13. Example Enterprise Tables

## revenue

```text
id UUID PK
period_start DATE
period_end DATE
department_id UUID nullable
revenue NUMERIC
currency TEXT
source_version TEXT
created_at TIMESTAMPTZ
```

## transactions

```text
id UUID PK
customer_id UUID
product_id UUID
transaction_time TIMESTAMPTZ
amount NUMERIC
currency TEXT
status TEXT
department_id UUID nullable
```

## customers

```text
id UUID PK
customer_code TEXT UNIQUE
name TEXT
segment TEXT
region TEXT
created_at TIMESTAMPTZ
```

For sensitive-demo behavior, include synthetic fields that can trigger privacy policy without containing real personal information.

---

# 14. Conversations

## conversations

```text
id UUID PK
customer_id UUID nullable
department_id UUID nullable
started_at TIMESTAMPTZ
ended_at TIMESTAMPTZ nullable
access_level TEXT
```

## conversation_messages

```text
id UUID PK
conversation_id UUID FK
sender_type TEXT
sender_id TEXT nullable
message_text TEXT
timestamp TIMESTAMPTZ
sensitivity TEXT
```

The authoritative conversation history remains PostgreSQL.

Qdrant may contain embeddings for semantic retrieval.

---

# 15. Evaluation Database

## cases

```text
id UUID PK
case_type TEXT
query TEXT
domain TEXT
source_dataset TEXT nullable
split TEXT
difficulty TEXT
created_at TIMESTAMPTZ
```

## annotations

```text
id UUID PK
case_id UUID FK
annotator_type TEXT
correctness TEXT
grounding TEXT
safety TEXT
privacy TEXT
reasoning TEXT
action_risk TEXT
preferred_intervention TEXT nullable
why TEXT nullable
created_at TIMESTAMPTZ
```

The current data specification defines the human labels and requires provenance for every label. fileciteturn2file5L1183-L1284

---

# 16. Benchmark Runs

## benchmark_runs

```text
id UUID PK
benchmark_name TEXT
dataset_version TEXT
model_version TEXT
algorithm_version TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ nullable
config JSONB
results JSONB
```

This lets you compare:

```text
baseline
vs
ControlPlane
```

using quality, factuality, grounding, safety, recovery, cost, latency and other metrics specified by the data workstream. fileciteturn2file1L193-L225

---

# 17. Required Indexes

Initial indexes:

```text
requests(trace_id)
requests(session_id)
requests(created_at)

query_profiles(request_id, version)

plans(request_id)
plan_versions(plan_id, version)

execution_nodes(plan_version_id, status)

decisions(request_id, created_at)
interventions(request_id, created_at)

evaluations(request_id, created_at)

event_index(request_id, observed_at)
event_index(trajectory_id, observed_at)
event_index(event_type, observed_at)

trajectories(request_id)
trajectory_steps(trajectory_id, sequence_number)

execution_ledger(trajectory_id, sequence_number)
execution_ledger(occurred_at)

execution_metrics(request_id, timestamp)
```

Do not over-index before measurement.

---

# 18. Transaction Boundaries

For important state transitions:

```text
decision
+
plan version
+
state update
```

should be made consistent in PostgreSQL.

Event publication may then occur through a durable/outbox-style mechanism later if required.

For the prototype, do not create distributed transactions across PostgreSQL, Redis and MCP.

---

# 19. What PostgreSQL Does NOT Store

Do not store:

```text
raw API secrets
passwords
access tokens
private keys
unbounded raw model streams
duplicate vector indexes
large source documents inside every execution row
```

Use references where appropriate.

---

# 20. Prototype Schema Principle

Prefer:

```text
structured identifiers
+
relational fields
+
JSONB for variable metadata
+
foreign-key relationships
+
append-only consequential records
```

Avoid both extremes:

```text
everything normalized into hundreds of tiny tables
```

and:

```text
one giant JSON document per request
```

---

# 21. Schema Evolution

Every algorithm-dependent output must include a version.

Examples:

```text
query_profile_version
evaluator_algorithm_version
policy_version
plan_version
event_schema_version
model_version
dataset_version
```

Never silently reinterpret old records using a new algorithm.

