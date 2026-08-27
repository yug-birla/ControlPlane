# ControlPlane.ai — PostgreSQL Schema Contract

**Status:** Prototype Database Contract  
**Database:** PostgreSQL  
**Purpose:** Define the relational schema for authoritative ControlPlane state, trajectory/ledger data, capability metadata, and synthetic enterprise/evaluation data.

> This document defines logical schema and relationships. Physical partitioning/index tuning can evolve after measurement.

**Implementation status (Milestone 1, 2026-08-27):** `requests` (SS3.1), `trajectories`/`trajectory_steps` (SS9), `execution_ledger` (SS10.1), `event_index` (SS8.1), and `model_invocations` (SS10.2, new) are implemented — see `controlplane/db/models.py`, managed by Alembic (`alembic/versions/`). One deviation from this document's literal DDL, recorded in `docs/PROJECT_STATE/DECISIONS.md`: all `*_id`/`id` identifier columns are `TEXT`, not `UUID`, because Layer 1 already decided identifiers are prefixed strings (`req_<uuid4>`, `trace_<uuid4>`, `traj_<uuid4>`, ...) for log readability, and a native Postgres `UUID` column cannot hold that prefix. All other tables in this document remain design-only (not yet implemented).

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

The architecture requires capability metadata so the planner reasons over capabilities instead of hard-coded implementations.

---

## 5.2 model_registry

Extended in Milestone 2 (2026-08-28) with `source`, `model_family`, `parameter_count`, `local_or_remote`, `hardware_requirements`, `license`, `revision` -- required to describe both local (Hugging Face) and remote (Groq) models, per `docs/PROJECT_STATE/DECISIONS.md`. `reasoning_strength`/`version` (originally documented here) were not implemented -- superseded by `model_family`/`revision`, which cover the same intent (a model's lineage/version identity) for the models actually registered so far.

```text
id UUID PK
model_key TEXT UNIQUE
provider TEXT
source TEXT
display_name TEXT
model_family TEXT nullable
capabilities JSONB
parameter_count BIGINT nullable
context_window INTEGER nullable
latency_class TEXT nullable
cost_class TEXT nullable
local_or_remote TEXT
hardware_requirements JSONB
license TEXT nullable
revision TEXT nullable
availability_status TEXT
known_strengths JSONB
known_weaknesses JSONB
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

Use the intervention taxonomy defined by the data workstream (`ANNOTATION_GUIDELINES.md`), extended with `ABORT` for the runtime case where no bounded recovery is possible (see `docs/architecture/FAILURE_AND_RECOVERY.md`):

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
ABORT
```

This runtime enum uses `ABORT` (not `OTHER`) because a system-emitted decision must always resolve to a concrete action; `OTHER` is reserved for the human-annotation vocabulary (`annotations.preferred_intervention`, §15.2) where an annotator needs an escape hatch the fixed list doesn't cover.

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

The product thesis defines evaluation as modular with structured score/confidence/evidence/issues/recommendation output.

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

The Event Model requires events to carry structured identifiers, source, timestamps, version and normalized semantics.

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

The trajectory contract defines the ledger as an append-only record of consequential execution facts.

---

## 10.2 model_invocations

New this milestone. `docs/architecture/TRAJECTORY_AND_LEDGER.md` SS13.1 describes a conceptual "Model Invocation Record" but never gave it a concrete table; this is that table. It is the single authoritative copy of a model call's full input/output text — `execution_ledger` and `event_index` reference it by ID rather than duplicating the text (per SS15 in `docs/architecture/EVENT_MODEL.md`: "Do not duplicate complete payloads unnecessarily").

```text
id UUID PK
request_id UUID FK
trace_id UUID/UUID-like
trajectory_id UUID FK
provider TEXT
model TEXT
status TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ nullable
latency_ms BIGINT nullable
input_tokens BIGINT nullable
output_tokens BIGINT nullable
estimated_cost NUMERIC nullable
input_text TEXT nullable
output_text TEXT nullable
error_metadata JSONB nullable
```

`status` values: `SUCCESS`, `FAILURE`. `input_text`/`output_text` hold the visible prompt/response only — never hidden chain-of-thought/reasoning tokens, even if a provider's API response includes them.

Every `MODEL_INVOKED` ledger entry (SS10.1) carries `evidence_refs: {"model_invocation_id": ...}` pointing here.

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

The data workstream explicitly requires a synthetic enterprise environment and forbids use of real confidential data.

The `enterprise_demo` schema implements a synthetic consulting company ("NexaConsult Global"). This is the schema actually created by `data/synthetic_enterprise/init_postgres_schema.sql`, which this section documents:

```text
departments
employees
employee_skills
clients
projects
project_allocations
revenue
timesheets
expenses
invoices
support_tickets
okrs
performance_reviews
conversations
conversation_messages
service_catalog
```

All synthetic records should have stable IDs.

> **Relationship to `data/synthetic_enterprise/database/*.csv`:** Those 8 CSV files (`customers`, `departments`, `employees`, `orders`, `products`, `revenue_monthly`, `support_tickets`, `transactions`) are a separate, simpler flat-file dataset with a different (SaaS/e-commerce) business shape and different column sets. They are **not** loaded into the `enterprise_demo` schema above and have not been reconciled with it. Do not assume the two describe the same tables — see `DATASET_GAPS.md`.

---

# 13. Example Enterprise Tables

## clients

```text
id UUID PK
client_code TEXT UNIQUE
name TEXT
industry TEXT
segment TEXT
region TEXT
country TEXT
account_owner_id UUID FK -> employees
annual_revenue_usd NUMERIC nullable
relationship_start DATE nullable
status TEXT
created_at TIMESTAMPTZ
```

## projects

```text
id UUID PK
project_code TEXT UNIQUE
name TEXT
client_id UUID FK
department_id UUID FK nullable
project_type TEXT
status TEXT
lead_employee_id UUID FK nullable
start_date DATE
end_date DATE nullable
planned_end_date DATE nullable
contract_value_usd NUMERIC nullable
budget_usd NUMERIC nullable
actual_spend_usd NUMERIC
delivery_model TEXT nullable
region TEXT nullable
sow_reference TEXT nullable
created_at TIMESTAMPTZ
```

## revenue

```text
id UUID PK
period_start DATE
period_end DATE
project_id UUID FK nullable
department_id UUID FK nullable
client_id UUID FK nullable
revenue_usd NUMERIC
revenue_type TEXT
currency TEXT
fx_rate NUMERIC
created_at TIMESTAMPTZ
```

## timesheets

```text
id UUID PK
employee_id UUID FK
project_id UUID FK nullable
week_start DATE
billable_hours NUMERIC
non_billable_hours NUMERIC
overtime_hours NUMERIC
status TEXT
approved_by UUID FK nullable
submitted_at TIMESTAMPTZ nullable
approved_at TIMESTAMPTZ nullable
```

For sensitive-demo behavior, include synthetic fields that can trigger privacy policy without containing real personal information (e.g. `employees.base_salary`, `clients.annual_revenue_usd`).

---

# 14. Conversations

## conversations

```text
id UUID PK
client_id UUID FK nullable
project_id UUID FK nullable
employee_id UUID FK nullable
channel TEXT
subject TEXT nullable
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

This domain persists the evaluation-workstream datasets described in `docs/DATA/DATASET_REGISTRY.md`. `cases` is the shared parent row; `case_type` selects which of `responses`, `annotations`, `intervention_labels`, or `trajectory_labels` applies to a given case.

## 15.0 query_profiles (evaluation-scoped)

Purpose: the generated/evaluation query-profile dataset (`docs/DATA/QUERY_PROFILES.json`, `data/raw/generated/query_profiles_large.json`), kept separate from `controlplane.query_profiles` (§3.2), which holds live-request query profiles.

```text
id UUID PK
query_id TEXT UNIQUE
query TEXT
intent TEXT
domain TEXT
knowledge_type TEXT
required_data_sources JSONB
required_capabilities JSONB
complexity TEXT
risk TEXT
actionability TEXT
sensitivity TEXT
ambiguity TEXT
expected_route TEXT
taxonomy_labels JSONB
provenance TEXT
source_dataset TEXT nullable
source_license TEXT nullable
failure_mode TEXT nullable
generation_date DATE nullable
prompt_version TEXT nullable
validation_method TEXT nullable
created_at TIMESTAMPTZ
```

Fields and allowed values match `data/schemas/query_profile.schema.json` and `docs/DATA/SCHEMA.md`.

## 15.1 cases

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

`case_type` values: `QUERY_PROFILE`, `RAG`, `INTERVENTION`, `COUNTERFACTUAL`, `AGENT_TRAJECTORY`, `ANNOTATION`. `split` uses the values defined in `EVALUATION_PROTOCOL.md` (`TRAIN`, `VALIDATION`, `TEST`, `CHALLENGE`). `difficulty` uses the balance-target categories defined in `DATA_QUALITY.md`.

## 15.2 responses

Purpose: one row per model-generated response to a query, prior to any human or judge evaluation.

```text
id UUID PK
case_id UUID FK
model_id UUID nullable
response_text TEXT
input_tokens BIGINT nullable
output_tokens BIGINT nullable
latency_ms BIGINT nullable
estimated_cost NUMERIC nullable
provenance TEXT
created_at TIMESTAMPTZ
```

See `DATASET_GAPS.md`: no real model responses have been generated yet; this table is currently empty in the prototype.

## 15.3 annotations

```text
id UUID PK
case_id UUID FK
response_id UUID FK nullable
provenance TEXT
correctness TEXT
grounding TEXT
safety TEXT
privacy TEXT
reasoning TEXT
action_risk TEXT
preferred_intervention TEXT nullable
why TEXT nullable
double_annotated BOOLEAN
adjudicated_label TEXT nullable
agreement_rate NUMERIC nullable
created_at TIMESTAMPTZ
```

Vocabulary from `ANNOTATION_GUIDELINES.md` v0.1. `provenance` uses the values `HUMAN | EXPERT | LLM_JUDGE | AUTOMATIC | SYNTHETIC | DERIVED` and is required on every row (see `DATA_QUALITY.md`). `preferred_intervention` uses the 16-value annotation intervention vocabulary (`ANNOTATION_GUIDELINES.md`, includes `OTHER`).

## 15.4 judgments

Purpose: one row per LLM-judge evaluation of a response (distinct from `annotations`, which may be human, expert, or judge-sourced; `judgments` is specifically the structured judge output described in `MODEL_AND_EVALUATION_DECISIONS.md`).

```text
id UUID PK
case_id UUID FK
response_id UUID FK nullable
judge_model_id UUID nullable
judge_version TEXT
correctness NUMERIC nullable
relevance NUMERIC nullable
grounding NUMERIC nullable
reasoning NUMERIC nullable
safety NUMERIC nullable
privacy NUMERIC nullable
confidence NUMERIC nullable
issues JSONB
evidence_refs JSONB
created_at TIMESTAMPTZ
```

## 15.5 intervention_labels

Purpose: persists the intervention dataset described in `CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md` §14 (`data/raw/generated/intervention_cases.json`).

```text
id UUID PK
case_id UUID FK
initial_route TEXT
failure TEXT
severity TEXT
evidence TEXT
possible_interventions JSONB
preferred_intervention TEXT
reason TEXT
expected_effect TEXT nullable
cost_effect TEXT nullable
latency_effect TEXT nullable
risk_effect TEXT nullable
provenance TEXT
created_at TIMESTAMPTZ
```

## 15.6 trajectory_labels

Purpose: persists the agent trajectory dataset described in `CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md` §18 (`data/raw/generated/agent_trajectories.json`).

```text
id UUID PK
case_id UUID FK
trajectory_type TEXT
user_request TEXT
plan JSONB
steps JSONB
final_action TEXT
final_answer TEXT
risk TEXT
intervention_point INTEGER nullable
expected_control_action TEXT
provenance TEXT
created_at TIMESTAMPTZ
```

`trajectory_type` uses the values `SAFE | UNSAFE | RECOVERABLE | UNRECOVERABLE | WRONG_TOOL | UNNECESSARY_TOOL | HUMAN_APPROVAL_REQUIRED`.

---

# 16. Benchmark Runs

## 16.1 benchmark_runs

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

using quality, factuality, grounding, safety, recovery, cost, latency and other metrics specified by the data workstream.

## 16.2 experiment_runs

Purpose: one row per BASELINE-vs-CONTROLPLANE comparison run (`EVALUATION_PROTOCOL.md` "Comparison Experiment"), as distinct from `benchmark_runs`, which scores a single system/algorithm version against a dataset rather than comparing two systems.

```text
id UUID PK
experiment_name TEXT
dataset_version TEXT
baseline_config JSONB
controlplane_config JSONB
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ nullable
metrics JSONB
```

`metrics` holds the per-metric baseline-vs-ControlPlane comparison values listed in `EVALUATION_PROTOCOL.md` (quality, factuality, grounding, safety, recovery rate, cost, latency, model calls, tool calls). Do not populate `metrics` until the experiment has actually been run (see `DATASET_GAPS.md`).

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

cases(case_type, split)
annotations(case_id)
intervention_labels(case_id)
trajectory_labels(case_id)
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

