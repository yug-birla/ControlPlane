# ControlPlane.ai — Retrieval, RAG Adequacy, Factuality & Hallucination Implementation Guide

## Purpose

This document instructs the coding agent how to implement the **retrieval, RAG adequacy, factuality, and hallucination-detection subsystem** without prematurely over-engineering or fine-tuning components that do not yet need it.

This document is a technical implementation contract. It must remain consistent with:

1. `AGENTS.md`
2. `PRODUCT_THESIS.md`
3. `docs/ARCHITECTURE.md`
4. `docs/ARCHITECTURE/RUNTIME_FLOW.md`
5. `docs/ARCHITECTURE/EVENT_MODEL.md`
6. `docs/ARCHITECTURE/TRAJECTORY_AND_LEDGER.md`
7. `docs/ARCHITECTURE/FAILURE_AND_RECOVERY.md`
8. `docs/ARCHITECTURE/SCALE_ARCHITECTURE.md`

Do not replace those documents. This file specifies the implementation strategy for one bounded subsystem.

---

# 1. Final Architectural Decision

The subsystem is divided into three distinct responsibilities:

```text
RETRIEVAL
    ↓
RAG ADEQUACY
    ↓
GENERATION
    ↓
FACTUALITY / HALLUCINATION
    ↓
CONTROLPLANE DECISION
```

The system must NOT collapse these into one score.

### Retrieval asks:

> Can we find useful evidence?

### RAG adequacy asks:

> Is the evidence sufficient and appropriate for answering this query?

### Factuality/hallucination asks:

> Is the generated answer supported, internally consistent, and sufficiently trustworthy?

### ControlPlane asks:

> Given those signals plus risk, confidence, trajectory, policy, cost and latency, what should happen next?

This follows the architecture rule that evaluators report observations while ControlPlane remains the decision authority.

---

# 2. Target End-to-End Flow

Implement the following logical pipeline:

```text
USER QUERY
    ↓
QUERY PROFILE
    ↓
RETRIEVAL REQUEST
    ↓
┌─────────────────────────────────────┐
│ Hybrid Retrieval                    │
│                                     │
│ Dense Search + BM25                 │
└─────────────────────────────────────┘
    ↓
Rank Fusion
    ↓
Top-K Candidate Set
    ↓
Cross-Encoder Reranker
    ↓
Evidence Set
    ↓
RAG Adequacy Evaluator
    ↓
┌─────────────────────────────────────────────┐
│ SUFFICIENT / PARTIAL / INSUFFICIENT /      │
│ CONFLICTING                                │
└─────────────────────────────────────────────┘
    ↓
Generation
    ↓
Factuality / Hallucination Evaluation
    ↓
┌─────────────────────────────────────────────┐
│ SelfCheckGPT signal                         │
│ + Evidence/Claim Verification               │
│ + Independent LLM Judge                    │
└─────────────────────────────────────────────┘
    ↓
ControlPlane Decision
    ↓
PASS / VERIFY / RE-RETRIEVE / RE-RANK /
CHANGE MODEL / REGENERATE / REPLAN /
HUMAN / ABSTAIN / BLOCK
```

Do not implement this as an unconditional linear pipeline. The output of adequacy or factuality evaluation can emit events that cause ControlPlane to alter the execution graph.

---

# 3. Retrieval System

## 3.1 Baseline Retrieval Architecture

The baseline retrieval architecture is:

```text
Query
 ↓
Query normalization
 ↓
Dense retrieval
+
BM25 sparse retrieval
 ↓
Rank fusion
 ↓
Top 20–50 candidates
 ↓
Cross-encoder reranker
 ↓
Top 5–10 evidence chunks
 ↓
Evidence construction
```

### Baseline components

Use:

```text
Dense retriever:
1 pretrained embedding model

Sparse retriever:
BM25

Fusion:
Reciprocal Rank Fusion (RRF)

Reranker:
1 pretrained cross-encoder
```

Do not fine-tune these components initially.

---

# 4. Retrieval Research References

The coding agent must record the following research references in the relevant algorithm/research documentation:

### BM25

Use as the lexical retrieval baseline.

Purpose:

- exact terminology
- identifiers
- names
- numbers
- policy wording
- lexical matches

### Reciprocal Rank Fusion

Use to combine dense and lexical rankings.

Reference:

> Cormack, Clarke & Büttcher, *Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods*.

### ColBERTv2

Use as an advanced retrieval experiment/reference, not as the initial mandatory implementation.

Purpose:

- late-interaction retrieval
- stronger semantic retrieval while maintaining efficiency

The initial prototype should remain:

```text
Dense + BM25 + RRF + Cross-Encoder
```

unless experiments show a concrete reason to replace it.

---

# 5. Dense Retrieval Model

## Initial requirement

Use exactly:

```text
1 pretrained embedding model
```

Do not deploy multiple embedding models initially.

The embedding model should produce embeddings for:

```text
documents
chunks
queries
memory items
chat-history items
```

where relevant.

### Do not fine-tune initially

The first experiment must establish:

```text
pretrained baseline
→ evaluate
→ identify domain failure
```

Only then consider fine-tuning.

---

# 6. Reranker

Use:

```text
1 pretrained cross-encoder reranker
```

Purpose:

```text
Top 20–50 retrieved candidates
→ semantic reranking
→ top 5–10
```

Do not fine-tune initially.

### Fine-tuning condition

Fine-tune only if:

1. baseline retrieval has been measured,
2. domain-specific relevance errors are identified,
3. there are enough labeled query-document pairs,
4. the improvement target is clearly defined.

The training data, if later created, should look like:

```text
query
candidate_document
relevance_label
```

or pairwise:

```text
query
positive_document
negative_document
```

Do not fine-tune merely because compute is available.

---

# 7. Retrieval Output Schema

The retrieval service must return structured results.

Recommended logical schema:

```json
{
  "retrieval_run_id": "retrieval_...",
  "query_id": "query_...",
  "retrieval_version": "v1",
  "candidates": [
    {
      "document_id": "doc_...",
      "chunk_id": "chunk_...",
      "text": "...",
      "dense_score": 0.0,
      "bm25_score": 0.0,
      "fusion_score": 0.0,
      "reranker_score": 0.0,
      "rank_before_rerank": 0,
      "rank_after_rerank": 0,
      "source": "enterprise_rag",
      "metadata": {}
    }
  ],
  "selected_evidence": [
    {
      "document_id": "doc_...",
      "chunk_id": "chunk_...",
      "text": "...",
      "source": "...",
      "reranker_score": 0.0,
      "metadata": {}
    }
  ]
}
```

Do not store unnecessary sensitive text in logs. The execution ledger should store identifiers and provenance where possible, with content controlled by the data-retention policy.

---

# 8. Evidence Set Construction

After reranking:

```text
top 5–10 chunks
```

must be transformed into a normalized evidence set.

Perform:

- duplicate removal
- metadata preservation
- source attribution
- optional chunk stitching
- basic conflict detection
- provenance preservation

The evidence set should preserve:

```text
document_id
chunk_id
source
timestamp/freshness if available
retrieval scores
```

---

# 9. RAG Adequacy Is NOT Retrieval Quality

This distinction is mandatory.

A retrieval system can retrieve relevant documents while still failing to provide enough evidence to answer the user's question.

Therefore define:

```text
RETRIEVAL QUALITY
=
Are the retrieved items relevant?

RAG ADEQUACY
=
Is the evidence sufficient for the specific question?
```

These are separate signals.

---

# 10. RAG Adequacy Architecture

Implement:

```text
Evidence Set
    ↓
Context Relevance
    ↓
Evidence Coverage
    ↓
Answerability / Sufficiency
    ↓
Conflict Detection
    ↓
RAG Status
```

Output enum:

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
CONFLICTING
```

Also return:

```text
confidence
reasons
evidence_ids
missing_information
```

---

# 11. ARES as the Primary Research Reference

Use **ARES** as the principal research reference for the RAG evaluation design.

ARES evaluates:

```text
Context Relevance
Answer Faithfulness
Answer Relevance
```

It also provides a useful approach for using learned judges with a relatively small human-annotated calibration set.

Important:

**Do not simply copy ARES as the whole ControlPlane.**

Use the concepts to build our:

```text
RAG Adequacy
+
Faithfulness
+
Relevance
```

signals.

---

# 12. RAGAS as a Complementary Reference

Use RAGAS as a baseline/reference for RAG evaluation.

Do not make:

```text
RAGAS score
→ direct ControlPlane action
```

Instead:

```text
RAGAS-style signals
→ evaluation layer
→ ControlPlane decision
```

The architecture must treat RAG evaluation outputs as observations.

---

# 13. Evidence Sufficiency Evaluator

This is a ControlPlane-specific addition.

Input:

```text
query
evidence set
```

Output:

```text
SUFFICIENT
PARTIAL
INSUFFICIENT
CONFLICTING
```

Recommended initial implementation:

```text
heuristic evidence coverage
+
LLM evaluation
+
source/provenance checks
```

Do not immediately fine-tune a dedicated model.

---

# 14. RAG Adequacy Decision Examples

### Case A

```text
Query:
What is our Q4 revenue?

Evidence:
Document contains exact Q4 revenue.

Result:
SUFFICIENT
```

### Case B

```text
Query:
Why did revenue decline in Q4?

Evidence:
Revenue values are present but cause is absent.

Result:
PARTIALLY_SUFFICIENT
```

### Case C

```text
Query:
What is our Q4 revenue?

Evidence:
Q1, Q2 and Q3 information only.

Result:
INSUFFICIENT
```

### Case D

```text
Two authoritative documents give different numbers.

Result:
CONFLICTING
```

---

# 15. RAG Failure Recovery

If:

```text
RAG_STATUS = INSUFFICIENT
```

do not automatically generate an answer.

Emit:

```text
RETRIEVAL_INSUFFICIENT
```

Then ControlPlane decides:

```text
RETRIEVE_MORE
RERANK
CHANGE_DATA_SOURCE
SQL
WEB
ASK_CLARIFICATION
HUMAN_REVIEW
ABSTAIN
```

The selection must depend on:

```text
query profile
risk
available capabilities
policy
cost
latency
trajectory
```

---

# 16. Factuality / Hallucination Architecture

Factuality happens after generation.

Use multiple complementary signals:

```text
Generated Answer
        │
        ├── SelfCheckGPT
        │
        ├── Evidence / Claim Verification
        │
        └── Independent LLM Judge
                    ↓
              Factuality Engine
```

Return:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTED
UNCERTAIN
```

Do not collapse all of this into a single arbitrary probability.

---

# 17. SelfCheckGPT Usage

SelfCheckGPT is specifically useful for a **black-box model** where internal logits or hidden representations are unavailable.

Concept:

```text
Original prompt
     ↓
Generate multiple sampled responses
     ↓
Compare claims / consistency
     ↓
Disagreement signal
     ↓
Hallucination risk
```

Use this primarily as:

```text
consistency / hallucination signal
```

not as truth itself.

### Critical limitation

```text
high consistency
≠
factually true
```

A model can consistently repeat the same false claim.

Therefore SelfCheckGPT must be combined with evidence-based verification when evidence is available.

---

# 18. SelfCheckGPT Configuration

For the first baseline:

```text
number_of_samples = small, configurable
sampling_temperature = configurable
```

Do not hard-code a high sample count.

Measure:

```text
accuracy
latency
token cost
false positive rate
false negative rate
```

against a human-labeled hallucination subset.

Only increase sampling if the benefit justifies the added latency/cost.

---

# 19. Evidence / Claim Verification

For RAG or source-grounded queries:

```text
Answer
 ↓
Claim extraction
 ↓
Claim → evidence matching
 ↓
Supported / Contradicted / Unsupported
```

Claims should be linked to:

```text
document_id
chunk_id
source
```

Example:

```json
{
  "claim_id": "claim_1",
  "claim": "Q4 revenue was ₹100 crore.",
  "support": [
    {
      "document_id": "annual_report",
      "chunk_id": "chunk_73"
    }
  ],
  "status": "SUPPORTED"
}
```

This provides an audit trail for trust.

---

# 20. Independent LLM Judge

Use a separate evaluator role for:

```text
answer correctness
faithfulness
relevance
reasoning quality
```

Start with a strong general model using a strict rubric.

Research references:

### MT-Bench / Chatbot Arena

Study LLM-as-a-judge behavior, including known biases.

### Prometheus

Study specialized open evaluator models and rubric-based scoring.

Do not train a dedicated judge immediately.

---

# 21. Final Factuality Engine

Combine:

```text
SelfCheckGPT
+
Claim/Evidence Verification
+
LLM Judge
```

into structured signals:

```text
consistency_signal
evidence_support
contradiction_signal
judge_score
judge_confidence
```

Then ControlPlane interprets these signals.

Example:

```text
SelfCheck: LOW RISK
Evidence: UNSUPPORTED
Judge: LOW CONFIDENCE
```

Final:

```text
Factuality State:
UNSUPPORTED
```

and emit:

```text
VERIFICATION_FAILED
```

---

# 22. ControlPlane Must Own the Final Decision

The factuality subsystem must never directly decide:

```text
BLOCK
RETRIEVE_MORE
CHANGE_MODEL
```

Instead:

```text
Factuality evaluator
→ structured result/event
→ ControlPlane
→ policy + risk + trajectory + confidence
→ intervention
```

This preserves the system architecture.

---

# 23. Baseline → Research → Fine-Tune Strategy

Every intelligent component must follow:

```text
BASELINE
 ↓
MEASURE
 ↓
IDENTIFY FAILURE
 ↓
RESEARCH METHOD
 ↓
COMPARE
 ↓
ONLY THEN FINE-TUNE
```

## Baselines

### Retrieval

```text
BM25
+
dense retrieval
+
RRF
+
cross-encoder
```

### RAG adequacy

```text
LLM judge
+
simple evidence coverage
```

### Factuality

```text
SelfCheckGPT
+
evidence verification
+
LLM judge
```

### Query profiling

```text
rules + LLM
```

### Risk

```text
rules + policy
```

### Routing

```text
rules / heuristic routing
```

### Intervention

```text
policy rules
```

### Replanning

```text
structured rule/template planner
or constrained LLM planner
```

Do not start with fine-tuned routing or RL.

---

# 24. When Fine-Tuning Is Allowed

Fine-tuning is allowed only after:

```text
baseline implemented
+
evaluation dataset exists
+
failure mode measured
+
data is sufficient
+
expected improvement is defined
```

Strong candidates:

## A. RAG Evaluator

Use human-validated RAG cases.

Potentially fine-tune a lightweight evaluator inspired by ARES.

## B. Hallucination Detector

Use RAGTruth-style annotated data and internal annotations.

## C. Query Profiler

Use the 200–300 initial labeled profiles for exploratory training, but expand the dataset before making production-quality claims.

## D. Model Router

Use route comparison / preference / cost-quality data.

Study RouteLLM and related learned-routing work first.

---

# 25. Fine-Tuning Rules

Never:

```text
fine-tune because GPU is available
```

Always document:

```text
dataset version
label source
number of examples
model base
training objective
validation set
test set
baseline
fine-tuned result
cost
latency
failure cases
```

If fine-tuning does not improve the relevant metric enough to justify complexity, keep the baseline.

---

# 26. Data Requirements

Use three layers of data.

## Layer A — External Benchmarks

Use for component evaluation.

Relevant categories:

```text
RAG
hallucination
factuality
LLM judging
agent safety
retrieval
model routing
```

Potential references/datasets include:

```text
ARES
RAGAS
RAGTruth
HaluEval
InjecAgent
MT-Bench / preference-style data
```

Every external dataset must have:

```text
source
paper
license
version
download date
schema
label source
known limitations
```

---

# 27. Layer B — ControlPlane Custom Dataset

The custom dataset must model the actual control problem.

Target:

```text
200–300 query profiles
500–1,000 model responses
200–300 human-annotated cases
100–200 RAG cases
100–200 intervention cases
50–100 counterfactual cases
50–100 agent trajectories
```

These are planning targets, not quotas for low-quality data.

The important structure is:

```text
query
→ profile
→ capabilities
→ route
→ execution
→ event/failure
→ intervention
→ replan
→ outcome
→ quality/trust/cost/latency
```

---

# 28. Required Query Schema

Each query record should contain conceptually:

```json
{
  "query_id": "q_001",
  "query": "...",
  "intent": ["..."],
  "domain": "...",
  "knowledge_type": "...",
  "required_data_sources": ["..."],
  "required_capabilities": ["..."],
  "complexity": "...",
  "risk_profile": {
    "factuality": "...",
    "privacy": "...",
    "safety": "...",
    "action": "...",
    "financial": "..."
  },
  "actionability": "...",
  "sensitivity": "...",
  "ambiguity": "...",
  "expected_route": "..."
}
```

---

# 29. Required RAG Case Schema

```json
{
  "case_id": "rag_001",
  "query_id": "q_001",
  "query": "...",
  "candidate_documents": [],
  "retrieved_chunks": [],
  "selected_evidence": [],
  "context_relevance": "...",
  "evidence_sufficiency": "...",
  "conflict_status": "...",
  "ground_truth": "...",
  "expected_answer": "...",
  "failure_type": null,
  "preferred_intervention": null
}
```

---

# 30. Required Factuality Annotation Schema

```json
{
  "evaluation_id": "fact_001",
  "query_id": "q_001",
  "response_id": "resp_001",
  "claims": [
    {
      "claim_id": "c1",
      "claim": "...",
      "evidence_ids": ["chunk_73"],
      "status": "SUPPORTED"
    }
  ],
  "selfcheck_signal": "...",
  "judge_score": 0.0,
  "judge_confidence": 0.0,
  "overall_status": "PARTIALLY_SUPPORTED",
  "label_source": "HUMAN"
}
```

Never treat an LLM judge label as human ground truth.

---

# 31. Required Intervention Schema

```json
{
  "case_id": "int_001",
  "initial_route": "RAG",
  "failure": "RETRIEVAL_INSUFFICIENT",
  "severity": "high",
  "risk": {},
  "confidence": {},
  "available_interventions": [
    "RETRIEVE_MORE",
    "RERANK",
    "SQL",
    "ASK_CLARIFICATION",
    "ABSTAIN"
  ],
  "preferred_intervention": "SQL",
  "reason": "...",
  "expected_quality_effect": "increase",
  "expected_cost_effect": "increase",
  "expected_latency_effect": "increase"
}
```

---

# 32. Required Model Comparison Schema

For routing experiments:

```json
{
  "query_id": "q_001",
  "model_a": {
    "quality": 0.0,
    "latency_ms": 0,
    "cost": 0.0
  },
  "model_b": {
    "quality": 0.0,
    "latency_ms": 0,
    "cost": 0.0
  },
  "query_constraints": {
    "quality_threshold": 0.0,
    "latency_budget_ms": 0,
    "cost_budget": 0.0
  },
  "preferred_model": "model_b",
  "reason": "..."
}
```

This becomes training/evaluation data for a future learned router.

---

# 33. What the Data Team Must NOT Do

Do not create only:

```text
question → answer
```

Do not label everything with an LLM.

Do not use unlicensed data.

Do not mix evaluation/test examples into training.

Do not use real sensitive enterprise information.

Do not fabricate ground truth.

Do not fine-tune before establishing a baseline.

---

# 34. Recommended Storage Layout

```text
data/
├── raw/
│   ├── external/
│   └── generated/
│
├── processed/
│
├── annotations/
│   ├── query/
│   ├── rag/
│   ├── factuality/
│   ├── intervention/
│   └── trajectory/
│
├── evaluation/
│   ├── train/
│   ├── validation/
│   ├── test/
│   └── challenge/
│
├── synthetic_enterprise/
│   ├── database/
│   ├── documents/
│   └── chat/
│
└── schemas/
    ├── query.schema.json
    ├── rag_case.schema.json
    ├── factuality.schema.json
    ├── intervention.schema.json
    └── model_comparison.schema.json
```

---

# 35. Synthetic Enterprise RAG Environment

Create a synthetic environment rather than using real enterprise data.

Target:

```text
5–10 SQL tables
20–50 documents
50–100 chat-history records
```

Documents should include:

```text
HR policies
financial policies
security policies
product documents
customer policies
approval rules
technical documentation
```

Intentionally create:

```text
answerable
partially answerable
unanswerable
conflicting
outdated
irrelevant
```

cases.

---

# 36. Database/Storage Requirements

Minimum prototype:

```text
1 relational database
1 vector database
1 Redis-like service
```

Logical relational separation:

```text
controlplane state
enterprise demo data
```

Use one relational technology if convenient.

The vector store is for:

```text
RAG
memory
chat-history retrieval
```

The Redis-like service may provide:

```text
cache
rate limiting
short-lived state
event/queue transport
```

Do not make it the durable system of record.

---

# 37. MCP Requirements

Initial capability groups:

```text
1. Model
2. SQL/Data
3. RAG/Retrieval
4. Web/External Data
5. Agent/Tools
```

Potential future split:

```text
Memory/Chat
Verification
```

Do not create separate MCP servers merely for every function.

More importantly:

> **MCP is not the brain.**

ControlPlane owns:

```text
routing
risk
policy
evaluation
intervention
replanning
trust
```

MCP exposes capabilities.

---

# 38. Retrieval Evaluation Metrics

You need component-level metrics.

## Retrieval

Measure:

```text
Recall@K
Precision@K where ground truth exists
MRR
nDCG
reranker lift
```

## RAG adequacy

Measure:

```text
sufficiency accuracy
insufficiency recall
conflict detection
false-sufficient rate
false-insufficient rate
```

## Grounding

Measure:

```text
faithfulness
claim support rate
unsupported claim rate
contradiction rate
```

## Factuality

Measure:

```text
hallucination detection precision
hallucination detection recall
F1
false positive rate
false negative rate
```

---

# 39. ControlPlane-Level Metrics

The final evaluation is not only retrieval quality.

Measure:

```text
routing accuracy
failure detection
intervention accuracy
recovery success
answer quality improvement
risk reduction
cost change
latency change
model-call reduction
tool-call reduction
abstention correctness
human-escalation precision
```

The most important experiment is:

```text
BASELINE SYSTEM
vs
CONTROLPLANE SYSTEM
```

under the same workload.

---

# 40. Baseline System

Before claiming ControlPlane improvements, build a baseline:

```text
Query
 ↓
Fixed RAG / Fixed Model
 ↓
Answer
```

No adaptive intervention.

Then compare:

```text
Baseline
vs
ControlPlane
```

This is essential.

Otherwise there is no evidence that the control layer actually helps.

---

# 41. Prototype Implementation Order

Implement the subsystem in this order:

```text
1. Document ingestion
2. Chunking
3. Embedding
4. BM25
5. RRF
6. Reranker
7. Evidence schema
8. RAG generation
9. RAG adequacy baseline
10. ARES/RAGAS-style evaluation baseline
11. SelfCheckGPT baseline
12. Claim/evidence verification
13. Independent judge
14. ControlPlane factuality aggregation
15. Failure events
16. Replanning hooks
17. Evaluation experiments
18. Fine-tuning only if justified
```

Do not skip measurement between stages.

---

# 42. Important Architecture Invariants

The implementation must always preserve:

```text
Retrieval ≠ RAG adequacy
RAG adequacy ≠ factuality
Factuality ≠ final control decision
Evaluator ≠ ControlPlane
MCP ≠ ControlPlane
Evidence ≠ truth
Consistency ≠ truth
Confidence ≠ correctness
```

These distinctions are fundamental.

---

# 43. Final Recommended Prototype

The first serious implementation should be:

```text
                 QUERY
                   │
                   ▼
             Query Profile
                   │
                   ▼
         ┌─────────────────────┐
         │ HYBRID RETRIEVAL    │
         │ Dense + BM25        │
         └──────────┬──────────┘
                    ▼
                   RRF
                    ▼
              Cross-Encoder
                    ▼
              Evidence Set
                    ▼
             RAG ADEQUACY
          ┌─────────┼─────────┐
          ▼         ▼         ▼
      SUFFICIENT   PARTIAL  INSUFFICIENT
          │         │         │
          │         │         └──→ REPLAN
          └─────────┘
                    │
                    ▼
                GENERATION
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
   SelfCheckGPT  Evidence      Judge
                  Verify
        └───────────┼────────────┘
                    ▼
             FACTUALITY STATE
                    │
                    ▼
              CONTROLPLANE
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
         PASS     REPAIR    REPLAN
                    │
                    ▼
                 VERIFY
                    │
                    ▼
             ANSWER + TRUST
```

This is the **baseline architecture**, not the final set of algorithms.

---

# 44. Decision Rules for the Coding Agent

The coding agent must follow these rules:

### Do not fine-tune unless:

```text
baseline evaluated
+
failure identified
+
dataset sufficient
+
benefit hypothesis defined
```

### Do not add a model unless:

```text
its role is defined
+
current capability is insufficient
+
latency/cost impact is known
```

### Do not add a database unless:

```text
existing store cannot satisfy the state/data requirement
```

### Do not add an MCP server unless:

```text
there is a meaningful capability boundary
```

### Do not create an ML model if:

```text
rules/policy/telemetry can solve the problem reliably enough
```

### Do not let an evaluator:

```text
directly reroute
directly block
directly modify the execution graph
```

It should emit structured evidence/events. ControlPlane decides.

---

# 45. Research-to-Code Loop

For every component:

```text
Research paper
      ↓
Research note
      ↓
Problem definition
      ↓
Baseline
      ↓
Dataset
      ↓
Experiment
      ↓
Metric
      ↓
Comparison
      ↓
Decision
      ↓
Implementation
```

Document:

```text
why chosen
why alternatives rejected
what data supports it
what assumptions remain
what limitations exist
```

---

# 46. Final Principle

The subsystem must not become:

```text
RAG + RAGAS + SelfCheckGPT
```

as a collection of unrelated tools.

It must become:

```text
RETRIEVE
   ↓
ESTABLISH EVIDENCE
   ↓
ASSESS SUFFICIENCY
   ↓
GENERATE
   ↓
VERIFY
   ↓
REPORT STRUCTURED SIGNALS
   ↓
CONTROLPLANE DECIDES
   ↓
INTERVENE / REPLAN IF NECESSARY
```

The objective is not merely to tell the user:

> "This response may be hallucinated."

The objective is:

> **Detect the problem, understand why the current path is insufficient, choose a better path, execute it, verify the new result, and return the best trustworthy answer available within policy, cost, and latency constraints.**
