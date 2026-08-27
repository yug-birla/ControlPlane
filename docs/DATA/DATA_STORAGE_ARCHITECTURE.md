# ControlPlane.ai — Data & Storage Architecture

**Status:** Implementation Data Contract  
**Scope:** Competition Prototype / R2  
**Purpose:** Define the authoritative storage technologies, ownership boundaries, data placement, and persistence rules for ControlPlane.ai.

> This document locks the prototype storage choice. The higher-level architecture documents intentionally leave infrastructure implementation open; this document makes the concrete prototype decision.

---

# 1. Final Storage Decision

ControlPlane will use exactly three primary storage technologies for the prototype:

```text
1. PostgreSQL
   = authoritative structured state and relational data

2. Qdrant
   = semantic/vector retrieval

3. Redis
   = cache + event transport + rate limiting + short-lived coordination
```

We will **not** use Chroma DB or Pinecone as prototype dependencies.

The separation is:

```text
POSTGRESQL
    "What is authoritative and durable?"

QDRANT
    "What is useful for semantic retrieval?"

REDIS
    "What needs to be fast, temporary, cached, queued, or streamed?"
```

This preserves the architecture's required distinction between persistent execution state, event/queue transport, trajectory/ledger storage, and caching. The scale architecture explicitly separates these infrastructure responsibilities from ControlPlane intelligence.

---

# 2. Why This Architecture

The competition assumes 10,000 interactions/week, but individual interactions can produce many internal operations. The architecture therefore needs persistent state, event transport, caching, bounded concurrency, and observability without introducing unnecessary distributed infrastructure.

The storage design follows:

```text
                     CONTROLPLANE
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
     PostgreSQL        Qdrant            Redis
      durable           vector           fast/
      truth             retrieval        ephemeral
```

---

# 3. Database Responsibilities

## 3.1 PostgreSQL

PostgreSQL is the **system of record** for structured information.

Store:

```text
request/session metadata
query profiles
execution state
plans and plan versions
execution nodes
decisions
interventions
evaluations
policies
model registry
capability registry
route registry
trajectory metadata
execution ledger
human reviews
trust reports
cost/latency summaries
evaluation metadata
synthetic enterprise data
```

Do not use PostgreSQL as the vector search engine.

---

## 3.2 Qdrant

Qdrant is the **semantic retrieval system**.

Store embeddings and associated payload metadata for:

```text
enterprise documents
conversation semantic search
designated memory
optional evaluation corpus
```

Qdrant is an index/retrieval representation.

It is **not** the authoritative source of:

```text
execution state
policy
route history
human approvals
ledger facts
cost accounting
model registry
```

The authoritative source for those remains PostgreSQL.

---

## 3.3 Redis

Redis is the **fast infrastructure layer**.

Use it for:

```text
cache
rate limiting
short-lived coordination
event streams
temporary execution markers
background jobs where appropriate
```

Redis must not become the authoritative source of durable ControlPlane state.

If Redis is unavailable:

```text
persistent state must remain safe
```

The runtime may degrade by bypassing cache or temporarily reducing asynchronous features when policy permits.

---

# 4. Logical Data Domains

The system has six logical data domains:

```text
DOMAIN 1 — Identity / Request
DOMAIN 2 — Planning / Execution
DOMAIN 3 — Governance / Evaluation
DOMAIN 4 — Trajectory / Ledger
DOMAIN 5 — Capability / Infrastructure
DOMAIN 6 — Enterprise / Evaluation Data
```

These domains are logical boundaries.

They do not automatically require separate database servers.

---

# 5. PostgreSQL Logical Structure

Use one PostgreSQL deployment initially.

Recommended databases/schemas:

```text
PostgreSQL
|
+-- controlplane
|     +-- requests
|     +-- sessions
|     +-- query_profiles
|     +-- execution_states
|     +-- plans
|     +-- plan_versions
|     +-- execution_nodes
|     +-- decisions
|     +-- interventions
|     +-- evaluations
|     +-- trust_reports
|     +-- human_reviews
|     +-- policies
|     +-- model_registry
|     +-- capability_registry
|     +-- route_registry
|     +-- trajectories
|     +-- trajectory_steps
|     +-- execution_ledger
|     +-- model_invocations
|     +-- cost_latency_records
|     +-- event_index
|
+-- enterprise_demo  (NexaConsult Global synthetic company — see POSTGRES_SCHEMA.md §12)
|     +-- departments
|     +-- employees
|     +-- employee_skills
|     +-- clients
|     +-- projects
|     +-- project_allocations
|     +-- revenue
|     +-- timesheets
|     +-- expenses
|     +-- invoices
|     +-- support_tickets
|     +-- okrs
|     +-- performance_reviews
|     +-- conversations
|     +-- conversation_messages
|     +-- service_catalog
|
+-- evaluation
      +-- cases
      +-- query_profiles
      +-- responses
      +-- annotations
      +-- judgments
      +-- intervention_labels
      +-- trajectory_labels
      +-- benchmark_runs
      +-- experiment_runs
```

For the competition, these may all run on the same PostgreSQL instance.

---

# 6. Source-of-Truth Rules

## PostgreSQL is authoritative for:

```text
execution state
plan versions
decision history
interventions
human approvals
policies
model registry
capability registry
route registry
trajectory metadata
execution ledger
enterprise structured data
evaluation metadata
```

## Qdrant is authoritative only for:

```text
vector index contents
vector payload metadata required for retrieval
```

The original source documents remain outside Qdrant.

## Redis is authoritative for:

```text
nothing critical
```

Redis is infrastructure state, not durable business truth.

---

# 7. Document Storage

Original documents should remain in a filesystem/object-like data directory:

```text
data/
├── enterprise/
│   ├── documents/
│   ├── policies/
│   └── reports/
├── evaluation/
└── conversations/
```

Flow:

```text
Original Document
      |
      +--> PostgreSQL metadata
      |
      +--> chunking
             |
             +--> embeddings
                    |
                    +--> Qdrant
```

Do not make Qdrant the only copy of a source document.

---

# 8. Data Lifecycle

## Ingestion

```text
source
  ↓
validation
  ↓
metadata extraction
  ↓
chunking (where applicable)
  ↓
embedding
  ↓
Qdrant
  +
PostgreSQL metadata
```

## Query

```text
user query
  ↓
ControlPlane
  ↓
Qdrant / PostgreSQL / Redis
  ↓
normalized result
  ↓
ExecutionState
```

## Audit

```text
event
  ↓
PostgreSQL history/ledger
```

## Analytics

```text
event / state
  ↓
async aggregation
  ↓
evaluation / dashboard
```

---

# 9. Data Ownership Principle

Every data object must have one clear owner.

Examples:

```text
Query profile
→ ControlPlane

Enterprise revenue
→ enterprise_demo

Document source
→ source file / document store

Document embedding
→ Qdrant

Execution plan
→ PostgreSQL

Current transient execution marker
→ Redis

Final execution ledger fact
→ PostgreSQL

Model capability metadata
→ model_registry
```

Do not duplicate authoritative values across stores unless the duplication is explicitly defined as a cache/index.

---

# 10. IDs

All runtime objects must use stable IDs.

Recommended:

```text
request_id
session_id
trace_id
trajectory_id
plan_id
plan_version_id
node_id
event_id
decision_id
intervention_id
evaluation_id
ledger_entry_id
human_review_id
model_id
capability_id
route_id
document_id
chunk_id
tool_call_id
```

IDs must be globally unique within the relevant domain.

`trace_id` is used for cross-component observability.

`trajectory_id` identifies the governed execution trajectory.

---

# 11. Timestamp Rules

Use UTC for persisted timestamps.

Use:

```text
created_at
updated_at
started_at
completed_at
observed_at
```

for relevant entities.

Never use local machine time as the canonical persisted timestamp.

---

# 12. JSON Usage

Use relational columns for:

```text
IDs
status
type
timestamps
foreign keys
common filters
budget values
classification fields
```

Use JSON/JSONB for:

```text
variable query profiles
evidence references
model-specific metadata
event payloads
tool arguments/results where permitted
policy configuration
algorithm outputs
```

Do not put the entire database schema into unstructured JSON.

---

# 13. PII / Sensitive Data

The system is a prototype and should use synthetic enterprise information.

Do not ingest real confidential enterprise data.

For stored sensitive fields:

```text
minimize
classify
restrict
audit
```

For tool/agent records, do not store secrets, API keys, passwords, or credentials.

The architecture explicitly requires privacy/PII governance, access restrictions and trajectory-level data lineage.

---

# 14. Trajectory and Ledger Storage

Trajectory and ledger are logically separate.

```text
Trajectory Store
=
reconstructable execution state + workflow history

Execution Ledger
=
append-only consequential facts
```

This separation is explicitly defined by the trajectory contract.

For the prototype, both can live in PostgreSQL.

Do not introduce a separate ledger database unless actual requirements justify it.

---

# 15. Event Storage

The event model distinguishes:

```text
Event
Command
State Update
```

An event describes what happened.

A command instructs an operation.

A state update changes authoritative state.

The event transport may use Redis Streams.

The durable event/history record required for reconstruction should be represented in PostgreSQL.

---

# 16. Cache Rules

Cache only data with a defined invalidation policy.

Every cache entry must have:

```text
key
value
created_at
expires_at / TTL
version if relevant
namespace
```

Suggested cache namespaces:

```text
cp:query_profile:
cp:model_metadata:
cp:capability:
cp:retrieval:
cp:embedding:
cp:policy:
cp:benchmark:
```

Never assume a cached value is authoritative.

---

# 17. Development Environment

Use Docker Compose for the prototype:

```text
services:
  postgres
  qdrant
  redis
  controlplane-api
  worker
  dashboard
  optional mcp services
```

Do not introduce Kubernetes or Kafka by default.

The scale architecture explicitly favors production-compatible interfaces over production-level infrastructure complexity for this workload.

---

# 18. Final Architecture Decision

```text
POSTGRESQL
→ durable structured truth

QDRANT
→ vector retrieval

REDIS
→ cache + streams + transient coordination

FILES / OBJECT-LIKE STORAGE
→ original documents and datasets
```

This is the canonical prototype storage architecture.
