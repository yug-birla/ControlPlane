# ControlPlane.ai — Qdrant and Redis Data Contracts

**Status:** Prototype Infrastructure Contract  
**Purpose:** Define exactly what goes into Qdrant and Redis, how it is keyed, and what must never be treated as authoritative.

---

# 1. Qdrant Decision

## Use Qdrant as the single vector database.

Do not add Chroma DB or Pinecone to the prototype.

Rationale:

```text
Qdrant
=
local/self-hostable
+
persistent
+
metadata filtering
+
vector retrieval
+
good fit for RAG
+
simple Docker deployment
```

The rest of the architecture remains vector-database agnostic through the Retrieval capability contract.

---

# 2. Qdrant Is an Index, Not the Source of Truth

The rule is:

```text
PostgreSQL / source files
        ↓
authoritative data
        ↓
embedding pipeline
        ↓
Qdrant
        ↓
retrieval index
```

If Qdrant is rebuilt:

```text
original source
→ re-embed
→ recreate collection
```

No critical ControlPlane state should be lost.

---

# 3. Qdrant Collections

Start with:

```text
enterprise_documents
conversation_search
memory
```

Optional later:

```text
evaluation_corpus
```

Do not create separate collections for every department or query type.

Use payload filtering.

---

# 4. Collection: enterprise_documents

Purpose:

```text
enterprise policies
reports
manuals
financial documents
technical documents
```

Each point contains:

```text
id
vector
payload
```

Payload:

```json
{
  "document_id": "doc_001",
  "chunk_id": "doc_001_chunk_07",
  "document_type": "financial_policy",
  "department": "finance",
  "source_uri": "data/enterprise/documents/finance_policy.pdf",
  "version": "v3",
  "access_level": "internal",
  "sensitivity": "medium",
  "jurisdiction": "IN",
  "created_at": "2026-08-26T00:00:00Z",
  "updated_at": "2026-08-26T00:00:00Z"
}
```

The vector itself represents the chunk.

---

# 5. Document Identity

Never treat a Qdrant point ID as the canonical document identity.

Use:

```text
document_id
chunk_id
```

and retain the original source.

Relationship:

```text
document_id
    ↓
source document
    ↓
multiple chunk_ids
    ↓
Qdrant points
```

---

# 6. Retrieval Metadata

Every retrieved chunk should be able to return:

```text
document_id
chunk_id
source
document_type
access_level
sensitivity
version
retrieval_score
rerank_score
```

The RAG capability must expose source/chunk information, retrieval scores, source metadata and evidence adequacy to ControlPlane. fileciteturn2file2L532-L547

---

# 7. Access Control

Qdrant filters should incorporate access metadata.

Example concept:

```text
user/app policy
      ↓
allowed access_level
      ↓
Qdrant payload filter
      ↓
retrieval
```

Do not retrieve documents first and filter privacy/security afterward if the policy can prevent the retrieval.

---

# 8. Collection: conversation_search

The authoritative conversation history is PostgreSQL:

```text
conversations
conversation_messages
```

Qdrant contains semantic representations of messages or message groups.

Payload:

```json
{
  "conversation_id": "conv_001",
  "message_id": "msg_023",
  "customer_id": "cust_007",
  "timestamp": "2026-08-26T10:30:00Z",
  "access_level": "support",
  "sensitivity": "internal",
  "source": "chat_history"
}
```

Query flow:

```text
Query
 ↓
Qdrant semantic search
 ↓
message IDs
 ↓
PostgreSQL
 ↓
authoritative message content
```

This prevents the vector store from becoming the authoritative chat database.

---

# 9. Collection: memory

Only intentionally stored memory goes here.

Examples:

```text
user preference
conversation preference
explicit user instruction
long-term contextual fact
```

Do not automatically vectorize every message as permanent memory.

Payload:

```json
{
  "memory_id": "mem_001",
  "user_context_id": "user_001",
  "memory_type": "preference",
  "source": "explicit_user_memory",
  "created_at": "2026-08-26T00:00:00Z",
  "expires_at": null
}
```

---

# 10. Embedding Lifecycle

```text
source
 ↓
normalize
 ↓
chunk
 ↓
embed
 ↓
Qdrant upsert
 ↓
record embedding/model version
```

Store the embedding-model version in metadata or ingestion metadata.

If the embedding model changes:

```text
new model
→ new collection/version or controlled re-index
```

Do not mix incompatible embeddings without an explicit design.

---

# 11. Qdrant Retrieval Pipeline

Initial architecture:

```text
Query
 ↓
Dense retrieval
 +
optional lexical/hybrid retrieval
 ↓
candidate set
 ↓
reranker
 ↓
top evidence
 ↓
evidence adequacy evaluation
```

The exact retrieval algorithm remains a replaceable implementation.

---

# 12. Qdrant Failure Behavior

If Qdrant is unavailable:

```text
RAG route fails
 ↓
RETRIEVAL_FAILURE / RESOURCE_FAILURE
 ↓
ControlPlane
 ↓
replan / alternate source / abstain
```

Never silently fabricate the missing evidence.

---

# 13. Redis Decision

Use one Redis deployment.

Redis responsibilities:

```text
cache
event streams
rate limiting
short-lived state
bounded background queues
distributed coordination where actually required
```

Redis is not the system of record.

---

# 14. Redis Key Namespaces

Use explicit prefixes:

```text
cp:cache:
cp:rate:
cp:lock:
cp:exec:
cp:session:
cp:event:
cp:job:
```

Examples:

```text
cp:cache:model:<model_id>
cp:cache:retrieval:<hash>
cp:rate:<application_id>:<window>
cp:exec:<trajectory_id>
```

---

# 15. Cache Key Rules

Cache keys must include every input that materially changes the result.

For example:

```text
retrieval cache key
=
query_hash
+
collection
+
filter_context
+
embedding_model_version
+
retrieval_version
```

Do not use:

```text
query only
```

when permissions or filters affect retrieval.

---

# 16. Redis TTL Rules

Every cache entry must have a TTL unless it is explicitly a non-cache coordination object.

Examples:

```text
model metadata
→ hours

retrieval result
→ short / policy-dependent

rate limit
→ fixed window

temporary execution marker
→ bounded workflow lifetime
```

Exact TTL values are implementation decisions and should be validated with measurements.

---

# 17. Redis Event Streams

Use streams for internal asynchronous events such as:

```text
telemetry
dashboard updates
background evaluation
non-critical history processing
```

Critical decision semantics remain in ControlPlane.

The Event Model explicitly states that event transport carries observations; it does not contain business policy. fileciteturn2file6L1325-L1339

---

# 18. Event Stream Naming

Conceptually:

```text
cp.events.execution
cp.events.evaluation
cp.events.intervention
cp.events.telemetry
cp.events.learning
```

The exact stream count may be consolidated during implementation.

Do not create a stream for every event type.

---

# 19. Redis Consumer Responsibilities

Potential consumers:

```text
controlplane-decision
trajectory-persistence
dashboard
analytics
evaluation-worker
learning-worker
```

Only the ControlPlane decision consumer should be able to initiate governance decisions.

Dashboard/analytics consumers are read-side consumers.

---

# 20. Idempotency

All Redis events that may be retried must have:

```text
event_id
trace_id
trajectory_id
```

Consumers must tolerate duplicate delivery.

Persistent state updates should be idempotent.

---

# 21. Redis Failure

If Redis fails:

```text
cache
→ bypass where safe

async telemetry
→ buffer/degrade

rate limiting
→ fail-safe policy

critical durable state
→ PostgreSQL remains authoritative
```

Do not allow Redis failure to silently erase execution state.

---

# 22. What Never Goes in Redis

Do not rely on Redis as the only storage for:

```text
plans
decisions
human approvals
execution ledger
policies
model registry
capability registry
final trust reports
final results
enterprise records
```

These belong in PostgreSQL.

---

# 23. Combined Data Flow

## RAG

```text
Original document
 ↓
PostgreSQL metadata/files
 ↓
Embedding
 ↓
Qdrant
 ↓
Retriever
 ↓
Reranker
 ↓
Evidence
 ↓
ControlPlane
```

## SQL

```text
ControlPlane
 ↓
SQL Capability
 ↓
PostgreSQL enterprise_demo
 ↓
Structured result
 ↓
ControlPlane
```

## Conversation

```text
PostgreSQL conversation_messages
 ↓
Embedding
 ↓
Qdrant conversation_search
 ↓
Message IDs
 ↓
PostgreSQL authoritative content
 ↓
ControlPlane
```

## Events

```text
Capability
 ↓
Redis Stream
 ↓
ControlPlane consumer
 ↓
PostgreSQL durable state/history
 ↓
Decision/Replan
```

---

# 24. Final Storage Contract

The final rule is:

```text
                 AUTHORITATIVE
                      ↓
                 PostgreSQL
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
    ControlPlane   Enterprise    Evaluation
       State          Data          Data


                  RETRIEVAL INDEX
                      ↓
                    Qdrant
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
      RAG          Chat Search     Memory


                   FAST LAYER
                      ↓
                    Redis
                      │
       ┌──────────────┼──────────────┐
       ↓              ↓              ↓
     Cache          Events       Rate Limits
```

**One authoritative truth per data domain.**

No component may silently become a second source of truth.
