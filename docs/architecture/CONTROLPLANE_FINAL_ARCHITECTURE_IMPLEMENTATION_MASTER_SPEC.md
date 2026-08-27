# ControlPlane.ai — Final Architecture & Implementation Master Specification

**Status:** Master implementation-planning specification  
**Scope:** Competition Prototype / R2  
**Purpose:** Consolidate the current architecture contracts and implementation decisions into one actionable plan before coding the final system.

---

# 0. Source-of-Truth Order

When documents disagree, use this order:

1. `AGENTS_RESEARCH_ALIGNED_UPDATED.md`
2. `ControlPlane_High_Level_Architecture_OPTIMAL.md`
3. `RUNTIME_FLOW.md`
4. `EVENT_MODEL.md`
5. `TRAJECTORY_AND_LEDGER.md`
6. `FAILURE_AND_RECOVERY.md`
7. `SCALE_ARCHITECTURE_UPDATED(1).md`
8. Component implementation contracts:
   - `CONTROLPLANE_ROUTING_SYSTEM_SPEC.md`
   - `CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md`
   - `FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md`
   - `INTERVENTION_ENGINE_IMPLEMENTATION_SPEC.md`
9. Concrete data/storage/model decisions:
   - `MODEL_AND_EVALUATION_DECISIONS.md`
   - `DATA_STORAGE_ARCHITECTURE.md`
   - `POSTGRES_SCHEMA.md`
   - `QDRANT_REDIS_DATA_CONTRACT.md`
10. `CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md`

Older architecture revisions are reference only and must not override the current contracts.

---

# 1. Final Product Definition

ControlPlane is:

> **An adaptive runtime AI control plane that transforms a request into a dynamic execution plan, coordinates models, data sources, retrieval systems, tools and verifiers, continuously evaluates execution, detects quality/cost/responsibility failures, dynamically intervenes and replans, governs unsafe actions, and returns the best available answer or action with evidence, trust, limitations, and audit history.**

The governed object is the **execution trajectory**, not only the final response.

```text
QUERY
  ↓
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
INTERVENE / REPLAN
  ↓
VERIFY
  ↓
RESPOND / ACT
  ↓
AUDIT + LEARN
```

Do not reduce the product to:

- a router
- an evaluator
- a RAG checker
- a safety filter
- an observability dashboard
- an MCP demo

Those are capabilities inside ControlPlane.

---

# 2. Final Architecture

```text
                               USER / CLIENT
                                     │
                                     ▼
                              API / GATEWAY
                                     │
                                     ▼
                           QUERY INTELLIGENCE
                     ┌───────────────┼────────────────┐
                     │               │                │
                  Intent          Risk           Capability
                 Profile        Profile            Need
                     └───────────────┼────────────────┘
                                     ▼
                                POLICY ENGINE
                                     │
                                     ▼
                            CAPABILITY DISCOVERY
                                     │
                                     ▼
                              INITIAL PLANNER
                                     │
                                     ▼
                           DYNAMIC EXECUTION GRAPH
                                     │
                 ┌───────────────────┼────────────────────┐
                 │                   │                    │
                 ▼                   ▼                    ▼
              MODELS                DATA                 AGENTS
                 │                   │                    │
        ┌────────┼───────┐    ┌──────┼──────┐      ┌──────┼─────┐
        ▼        ▼       ▼    ▼      ▼      ▼      ▼            ▼
      Fast    Medium  Strong  SQL   RAG    Web    Tools       APIs
                 │                   │                    │
                 └───────────────────┼────────────────────┘
                                     ▼
                          TRAJECTORY + EXECUTION LEDGER
                                     │
                                     ▼
                              EVALUATION LAYER
                                     │
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                        ▼
         QUALITY                   RISK                    DRIFT
         GROUNDING              PRIVACY/PII              TRAJECTORY
         FACTUALITY              SAFETY                 LINEAGE
         REASONING               ACTION RISK
                                     │
                                     ▼
                           RISK × CONFIDENCE ×
                        POLICY × IMPACT × BUDGET
                                     │
                                     ▼
                              DECISION ENGINE
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
           CONTINUE              INTERVENE              ESCALATE
              │                      │                      │
              │              ┌───────┼────────┐             ▼
              │              ▼       ▼        ▼         HUMAN /
              │           REPAIR   REROUTE   VERIFY    ABSTAIN/BLOCK
              │                      │
              └──────────────────────┼──────────────────┐
                                     ▼                  │
                                  REPLANNER              │
                                     │                  │
                                     ▼                  │
                           NEW EXECUTION PLAN           │
                                     │                  │
                                     └──────→ EXECUTE ───┘
                                                │
                                                ▼
                                            VERIFY
                                                │
                                                ▼
                                      TRUST + EVIDENCE
                                                │
                                                ▼
                                             OUTPUT
                                                │
                                         ASYNC LEARNING
```

---

# 3. Final Component Inventory

These are recommended prototype quantities.

| Component | Quantity | Fine-tune initially? |
|---|---:|---|
| Very-small generation model role | 1 | No |
| Medium generation model role | 1 | No |
| Strong reasoning model role | 1 | No |
| Independent judge/evaluator role | 1 | No initially |
| Query/risk local model | 0 initially; 1 later if needed | Optional |
| Embedding model | 1 | No |
| Reranker | 1 | No |
| PostgreSQL deployment | 1 | N/A |
| Qdrant | 1 | N/A |
| Redis | 1 | N/A |
| API service | 1 | N/A |
| ControlPlane orchestrator | 1 logical service initially | N/A |
| Dashboard | 1 | N/A |
| MCP capability groups | ~5 | N/A |
| Core evaluator modules | 8 | Mostly non-ML initially |
| Deterministic monitors | 3–4 | No |
| Intervention engine | 1 | No initially |
| Replanner | 1 | No initially |
| Trust/evidence aggregator | 1 | No initially |
| Human review mechanism | 1 | No |
| Trajectory store | 1 logical subsystem | N/A |
| Execution ledger | 1 logical subsystem | N/A |

The routing contract recommends one fast generation role, one strong reasoning role, one evaluator role, zero local query-intelligence models initially, one embedding model, one reranker, and one intervention/replanner interface.

---

# 4. Final Answer-Model Pool

The current concrete model decision is:

```text
Qwen3 ~1.3B
    ↓
Qwen3 4B
    ↓
Grok API
```

The model decision record explicitly assigns these roles as very-small, medium, and strong-reasoning respectively.

## 4.1 Qwen3 ~1.3B

Use for:

```text
simple factual
short summaries
basic transformations
simple conversation
low-risk / latency-sensitive
```

Strategy:

```text
pretrained
+
prompting
+
routing
```

**No fine-tuning initially.**

## 4.2 Qwen3 4B

Use for:

```text
medium-complexity
normal RAG generation
moderate analysis
simple coding
non-extreme multi-step reasoning
```

**No fine-tuning initially.**

## 4.3 Grok API

Use for:

```text
difficult reasoning
complex synthesis
high-complexity analysis
difficult coding/reasoning
lower-tier model failure
```

It is an escalation capability, not the default.

---

# 5. Judge / Evaluation Model

Current decision:

> **Prometheus 2 — 7B-class evaluator**

It is not a user-facing answer model.

Use it for:

```text
correctness
relevance
grounding
reasoning quality
rubric quality
pairwise model comparison
```

It can evaluate direct responses and compare candidate responses.

## Fine-tuning decision

Do **not** fine-tune Prometheus 2 initially.

Required progression:

```text
Prometheus 2
+
explicit rubric
+
few-shot examples
        ↓
human validation
        ↓
measure reliability
        ↓
identify systematic ControlPlane-specific weakness
        ↓
only then consider specialization
```

The current decision record explicitly states that the first fine-tuning candidate should be the evaluator, not the answer models, and only after evidence of systematic weakness.

---

# 6. Local ML Strategy

## Initial requirement

```text
LOCAL ML MODELS REQUIRED NOW = 0
```

The governance specification explicitly recommends starting with:

```text
rules
+
policy
+
pretrained NER/PII
+
LLM evaluator
+
structured state
+
deterministic lineage
```

and introducing one small local model only if the evaluation demonstrates a concrete gap.

## Best later candidates

Choose **one**, not one per subsystem:

```text
Candidate A → query/risk classifier
Candidate B → RAG/hallucination evaluator
Candidate C → quality/rubric evaluator
```

---

# 7. Query Intelligence

## Responsibility

Convert a raw request into a versioned multi-dimensional profile:

```text
intent
domain
data requirements
complexity
sensitivity
impact
actionability
risk dimensions
```

## Initial implementation

Use:

```text
cheap deterministic signals
+
one shared lightweight query-intelligence inference where necessary
```

Do NOT make three consecutive LLM calls:

```text
LLM risk
→ LLM capability
→ LLM model router
```

The routing contract explicitly warns against this control-plane overhead and recommends one cheap query-intelligence inference feeding multiple downstream decisions.

## Later learned model

A compact encoder can eventually cover:

```text
MiniLM
DistilBERT
DeBERTa
or equivalent compact model
```

Evaluate:

```text
precision
recall
F1
high-risk false-negative rate
calibration
latency
memory
```

Fine-tuning is optional initially and should occur only after enough consistent internal annotation data exists.

---

# 8. Risk Profiler

## Output

```text
risk_vector:
  factuality
  reasoning
  privacy
  security
  bias
  action
  financial
  compliance
```

## Architecture

```text
R0
deterministic risk signals
      ↓
R1
small classifier if needed
      ↓
R2
deep LLM/policy escalation only for ambiguous/high-impact cases
```

The routing contract explicitly says deeper analysis should be reserved for critical actions, ambiguous requests, unknown risk classes, conflicting signals, high-impact domains, and low-confidence classification.

## Fine-tuning

No initial fine-tuning.

---

# 9. Capability Router

Decides what capabilities are needed:

```text
SQL
RAG
Web
Memory
Chat
Reasoning
Coding
Agent
Multi-source
```

Initial implementation:

```text
query profile
+
rules
+
capability registry
```

Later:

```text
small multi-label classifier
```

Do not use a separate LLM for each capability decision.

---

# 10. Model Router

The router must not be a simple classifier.

It should consider:

```text
query profile
risk
complexity
quality threshold
confidence
trajectory state
current route
cost budget
latency budget
model capability
previous failures
availability
```

Output:

```text
Qwen3 ~1.3B
Qwen3 4B
Grok
cascade/escalation
verify
```

The routing system explicitly requires cost/latency-aware selection and warns that the router must be cheaper than the expected benefit of routing.

## Research progression

```text
V0
rules/heuristics

V1
model-performance profiles

V2
small learned router

V3
preference/cost-aware routing

V4
adaptive learned routing
```

Study:

- RouteLLM
- model cascading
- confidence-aware routing

---

# 11. Retrieval Architecture

The RAG implementation contract separates:

```text
retrieval
→ RAG adequacy
→ generation
→ factuality/hallucination
→ ControlPlane decision
```

These must not be collapsed into one score.

## Retrieval pipeline

```text
Query
 ↓
Dense retrieval
 +
BM25
 ↓
Rank fusion
 ↓
Reranker
 ↓
Evidence set
```

## Required retrieval components

```text
1 embedding model
1 lexical retriever
1 vector DB
1 reranker
1 evidence-construction layer
```

No fine-tuning initially.

---

# 12. Qdrant

Current contract:

> **Qdrant is the single vector database.**

Do not add Chroma or Pinecone to the prototype.

Use collections:

```text
enterprise_documents
conversation_search
memory
```

Optional later:

```text
evaluation_corpus
```

Qdrant is an index, not the source of truth.

---

# 13. RAG Adequacy Engine

Question:

> **Is the available evidence sufficient and appropriate for answering this query?**

Not:

> Did retrieval return anything?

Output:

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
CONFLICTING
```

## Initial implementation

```text
retrieval features
+
evidence coverage
+
LLM evaluator
```

Research:

- ARES
- RAGAS
- RAGTruth

The RAG guide explicitly assigns RAG adequacy as a separate stage from retrieval quality and factuality.

---

# 14. Factuality / Hallucination Engine

Initial pipeline:

```text
generated response
 ↓
claim/evidence comparison
 ↓
judge
 ↓
consistency / hallucination signal
```

Possible later augmentation:

```text
SelfCheckGPT-style consistency signals
```

Do not store hidden chain-of-thought.

Evaluate observable claims, evidence, tool outputs, and structured reasoning artifacts where intentionally exposed.

---

# 15. Final Evaluation Layer

The current evaluation contract freezes eight governance components:

```text
1. Response Quality
2. Reasoning
3. Safety
4. Privacy / PII
5. Bias
6. Behavioral Drift
7. Action Risk
8. Permission / Data Lineage
```

They are not independent policy authorities or automatically separate services.

## Important

Their outputs are normalized observations.

The final control decision combines:

```text
policy
risk
confidence
impact
trajectory
budget
available capabilities
```

The evaluator itself does not decide:

```text
reroute
block
human
retrieve
change model
```

The ControlPlane Decision Engine does.

---

# 16. P0 vs P1 Evaluation Components

## P0

Implement first:

```text
Response Quality
Reasoning
Safety
Privacy/PII
Action Risk
Permission/Data Lineage
```

## P1

Add after the core control loop works:

```text
Behavioral Drift
Bias
```

This ordering is explicitly specified in the governance contract.

---

# 17. Privacy / PII

No dedicated large language model required.

Use:

```text
pretrained PII/NER
+
regex/patterns
+
field sensitivity
+
policy
```

Possible action:

```text
REDACT
CHANGE_DATA_SOURCE
HUMAN_REVIEW
BLOCK
```

---

# 18. Safety

Initial:

```text
rules
+
policy
+
LLM evaluator
+
trajectory/action signals
```

For agentic safety, later research can incorporate runtime trajectory governance.

Do not make a safety model the sole policy authority.

---

# 19. Bias

Initial:

```text
controlled test cases
+
paired demographic variants
+
LLM/rule evaluation
```

P1 only.

---

# 20. Behavioral Drift Monitor

Initial implementation should be deterministic/interpretable.

Compare:

```text
expected trajectory
vs
observed trajectory
```

Signals can include:

```text
tool-call frequency
data-source deviation
permission change
external destination
action sensitivity
workflow length
```

The output is a control signal, not a final decision.

---

# 21. Action Risk Evaluator

For each proposed external action:

```text
action
+
target
+
permissions
+
data
+
impact
+
trajectory
+
policy
```

Output:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

The decision engine maps this to:

```text
ALLOW
MODIFY
HUMAN_APPROVAL
BLOCK
```

---

# 22. Permission / Data Lineage

This is deterministic graph/state logic, not necessarily ML.

Track:

```text
actor
permission
data object
action
destination
agent
timestamp
```

Example:

```text
Agent A
 ↓
requests data
 ↓
Agent B permission
 ↓
sensitive record
 ↓
external tool
```

The ledger must make this reconstructable.

---

# 23. Intervention Engine

## Final answer to the question:

# Should the Intervention Engine be fine-tuned?

**No. Not initially.**

The current implementation contract explicitly requires:

```text
LOCAL ML MODELS REQUIRED = 0
```

for V0.

The initial engine should be:

```text
rules
+
policy
+
structured evaluator signals
+
pretrained components
+
trajectory state
+
candidate scoring
```

---

# 24. Intervention Engine Responsibility

It answers:

> **Given the current execution state and a ControlPlane decision, what bounded execution change should be applied?**

It transforms:

```text
observations
policy
risk
confidence
trajectory
budgets
available capabilities
current plan
```

into:

```text
intervention decision
→ execution change
→ post-intervention verification
```

This distinction is explicitly defined in the intervention contract.

---

# 25. Intervention Vocabulary

Implement the common vocabulary:

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

---

# 26. Intervention Algorithm — V0

The exact required order is:

```text
TRIGGER
 ↓
Normalize observations
 ↓
Load execution state
 ↓
Load trajectory
 ↓
Load policy
 ↓
Load remaining budgets
 ↓
Recovery eligibility gate
 ↓
Generate candidates
 ↓
Filter impermissible candidates
 ↓
Score candidates
 ↓
Select
 ↓
Persist
 ↓
Emit INTERVENTION_TRIGGERED
 ↓
Apply change
 ↓
Emit resulting events
 ↓
Replan if necessary
 ↓
Execute
 ↓
Verify
 ↓
Measure actual effect
```

This is the current implementation contract.

---

# 27. Intervention Candidate Generation

Generate candidates deterministically.

Example:

```text
RETRIEVAL_INSUFFICIENT
→
RETRIEVE_MORE
RERANK
CHANGE_DATA_SOURCE
ASK_CLARIFICATION
ABSTAIN
```

```text
REASONING_UNCERTAINTY
→
VERIFY
CHANGE_MODEL
INCREASE_COMPUTE
REGENERATE
ABSTAIN
```

```text
PRIVACY_RISK
→
REDACT
CHANGE_DATA_SOURCE
HUMAN_REVIEW
BLOCK
```

```text
HIGH-IMPACT EXTERNAL ACTION
→
VERIFY
HUMAN_REVIEW
BLOCK
ABORT
```

The implementation contract explicitly specifies this deterministic candidate-generation pattern.

---

# 28. Hard Gates Before Intervention Scoring

Before scoring:

```text
policy
risk limit
capability availability
budget
authorization
state consistency
side-effect constraints
```

must be satisfied.

The correct order is:

```text
HARD GATES
 ↓
candidate filtering
 ↓
soft scoring
 ↓
ranking
 ↓
selection
```

A high quality score must never override a forbidden action.

---

# 29. Intervention V0 Scoring

Use an interpretable baseline:

```text
intervention_score =
    expected_quality_gain
  + risk_reduction
  + evidence_gain
  + recovery_probability
  - cost_penalty
  - latency_penalty
  - switch_penalty
  - risk_increase
```

Normalize features and use configurable weights.

This is explicitly the required baseline, not the final research algorithm.

---

# 30. Should Intervention Eventually Be Learned?

Yes, **but only after V0 is measured**.

Roadmap:

```text
V0
rules + policy + budgets + trajectory + scoring

V1
better confidence
better evidence
better capability profiles
model disagreement

V2
small learned intervention model

V3
learned policy
(contextual bandits / policy learning / reward modeling)

V4
adaptive intervention policy
```

The intervention contract explicitly says not to build V2–V4 before V0 is measurable.

---

# 31. What could V2 look like?

Candidate local models:

```text
gradient boosted trees
small MLP
compact encoder
small instruction model
```

Inputs:

```text
query features
risk
confidence
drift
failure type
model state
cost
latency
remaining budgets
available capabilities
trajectory features
```

This is preferable to fine-tuning another large generative model.

The intervention contract explicitly proposes these as later candidates.

---

# 32. Intervention Dataset

Required initial target:

```text
100–200 intervention cases
50–100 counterfactual cases
```

Human annotations should include:

```text
preferred intervention
reason
expected effect
cost effect
latency effect
risk effect
```

These labels should only be used for ML after the schema and annotation quality are stable.

---

# 33. Replanner

## Important distinction

The **Replanner is not the same as the Intervention Engine**.

Intervention Engine:

> What bounded change should we apply?

Replanner:

> After the state changed, what is the new authoritative execution graph?

Runtime specification:

```text
Plan V1
 ↓
Execution
 ↓
New event/evidence
 ↓
Current plan no longer appropriate
 ↓
REPLAN_TRIGGERED
 ↓
Replanner proposes graph changes
 ↓
ControlPlane accepts authoritative plan
 ↓
PLAN_UPDATED
 ↓
Plan V2
 ↓
Execution resumes
```

---

# 34. Should the Replanner be fine-tuned?

**No, not initially.**

The first Replanner should be a **deterministic / structured planner backed by the ControlPlane state and capability registry**, potentially using a general reasoning model only for proposal generation when deterministic planning is insufficient.

Architecture:

```text
Current ExecutionState
+
Current Plan
+
Trigger Event
+
Policy
+
Capabilities
+
Budgets
        ↓
Replanner
        ↓
Candidate graph changes
        ↓
Hard constraints
        ↓
ControlPlane validation
        ↓
New authoritative Plan Version
```

The Replanner should not autonomously become policy authority.

---

# 35. Replanner Constraints

Every replan must respect:

```text
policy
risk threshold
available evidence
maximum retries
latency budget
cost budget
capability availability
human approval requirements
state consistency
```

These constraints are part of the canonical runtime contract.

---

# 36. Replanning Examples

## RAG failure

```text
V1:
RAG → Qwen3 4B

Event:
RETRIEVAL_INSUFFICIENT

V2:
query expansion
→ hybrid retrieval
→ rerank
→ Qwen3 4B
→ verify
```

## Reasoning failure

```text
V1:
Qwen3 4B

Event:
HIGH_REASONING_UNCERTAINTY

V2:
Grok
→ verifier
```

## Data source mismatch

```text
V1:
RAG

Event:
enterprise-authoritative-source-required

V2:
SQL
→ reasoning
→ verify
```

---

# 37. Replanner Algorithm Roadmap

```text
V0
deterministic graph templates + constraints

V1
LLM-assisted plan proposal
with strict structured output

V2
plan proposal ranking / selection
using execution outcomes

V3
learned planning/intervention policy
only after sufficient trajectory data
```

Do not fine-tune a planner before you have meaningful execution trajectories.

---

# 38. Trust Engine

The evaluation contract explicitly distinguishes **Response Quality** from the system's final trust engine.

Therefore:

> **Trust is an aggregation and explanation layer, not another standalone LLM judge.**

---

# 39. Trust Engine Inputs

Aggregate:

```text
quality evaluation
factuality
grounding
reasoning
safety
privacy
bias
action risk
trajectory risk
behavioral drift
model disagreement
source quality
evidence sufficiency
verification result
policy outcome
```

Also include:

```text
abstention status
human approval
intervention history
recovery status
```

---

# 40. Trust Engine Output

Do not initially output an uncalibrated arbitrary number like:

```text
trust = 0.873
```

Prefer:

```text
trust_level:
HIGH
MEDIUM
LOW
```

with structured evidence:

```text
reasons
supporting evidence
warnings
limitations
verification status
interventions
source references
```

Example:

```text
TRUST: HIGH

Why:
- authoritative SQL source
- deterministic result
- verification passed
- no unresolved conflicts

Limitations:
- analysis depends on Q4 dataset freshness
```

---

# 41. Should the Trust Engine be fine-tuned?

**No initially.**

Do not create a dedicated trust LLM.

Use:

```text
normalized evaluator outputs
+
source/evidence metadata
+
trajectory state
+
policy
+
verification
```

to produce the trust report.

Later, if calibration is a demonstrated problem:

```text
human trust judgments
+
system features
→
calibration model
```

But this should be a later research layer, not a core dependency.

---

# 42. Trust Is Not the Same as Confidence

Keep these separate:

```text
Model confidence
≠
Evaluator confidence
≠
ControlPlane trust
```

Trust is the **system-level conclusion** based on multiple signals.

---

# 43. Final Decision Engine

The Decision Engine consumes:

```text
risk
confidence
impact
policy
trajectory
evaluation
drift
budgets
available capabilities
```

and returns:

```text
PASS
MONITOR
VERIFY
INTERVENE
ESCALATE
HUMAN_REVIEW
ABSTAIN
BLOCK
```

The evaluator components do not make this final choice.

---

# 44. Storage Architecture

The prototype uses exactly three primary storage technologies:

```text
PostgreSQL
Qdrant
Redis
```

The storage contract explicitly freezes these choices.

## PostgreSQL

System of record:

```text
requests
query_profiles
execution_states
plans
plan_versions
execution nodes
decisions
interventions
trajectory state
ledger
human reviews
capability metadata
model metadata
synthetic enterprise data
evaluation data
```

The PostgreSQL contract uses one deployment initially with logical areas:

```text
controlplane
enterprise_demo
evaluation
```

## Qdrant

Use:

```text
enterprise_documents
conversation_search
memory
```

It is the semantic index, not source of truth.

## Redis

Use for:

```text
cache
event transport
rate limiting
short-lived coordination
```

Never use Redis as the authoritative ledger.

---

# 45. MCP Architecture

Use approximately five logical capability groups initially:

```text
1. Model
2. SQL/Data
3. RAG/Retrieval
4. Web/External Data
5. Agent/Tools
```

These may be implemented as fewer or more physical servers depending on deployment simplicity.

MCP provides:

```text
capability discovery
capability invocation
resource access
```

ControlPlane owns:

```text
routing
risk
policy
evaluation
intervention
replanning
trust
human escalation
```

MCP must never become the brain.

---

# 46. Event Model

Canonical semantic pattern:

```text
Capability
 ↓
Event
 ↓
Event Bus
 ↓
ControlPlane Decision
 ↓
Intervention / Replanner
 ↓
New Execution Step
```

The Event Bus is a communication mechanism; capabilities report what happened and ControlPlane decides what happens next.

Important event classes:

```text
QUERY_RECEIVED
QUERY_RECLASSIFIED
PLAN_CREATED
PLAN_UPDATED
ROUTE_STARTED
ROUTE_COMPLETED

DATA_REQUIRED
DATA_UNAVAILABLE
RETRIEVAL_INSUFFICIENT
EVIDENCE_CONFLICT

MODEL_CALLED
MODEL_FAILURE
MODEL_DISAGREEMENT
HIGH_REASONING_UNCERTAINTY

TOOL_CALLED
TOOL_FAILURE
HIGH_ACTION_RISK
PERMISSION_ESCALATION

PII_DETECTED
PRIVACY_RISK
SAFETY_RISK
BIAS_RISK
BEHAVIORAL_DRIFT_HIGH

EVALUATION_COMPLETED
VERIFICATION_FAILED

INTERVENTION_TRIGGERED
REPLAN_TRIGGERED
HUMAN_REVIEW_REQUIRED

FINAL_RESPONSE_GENERATED
```

---

# 47. Trajectory + Execution Ledger

The architecture explicitly separates:

```text
Trajectory Store
= reconstructable execution state + workflow history

Execution Ledger
= append-only consequential facts
```

Record:

```text
plan versions
routes
models
data/documents
permissions
tools
actions
external destinations
events
evaluations
interventions
human approvals
partial execution
```

Do not store hidden chain-of-thought.

Store structured decision rationale and observable execution facts.

---

# 48. Failure and Recovery

Every recovery follows:

```text
detect
 ↓
diagnose
 ↓
choose intervention
 ↓
replan
 ↓
execute/continue
 ↓
verify
 ↓
finish / degrade / escalate / abstain / block / abort
```

The system must never:

```text
retry forever
force an unsupported answer
claim rollback without rollback capability
silently increase autonomy
```

These are explicit non-negotiable recovery rules.

---

# 49. Scale

The competition workload assumption is:

```text
10,000 interactions/week
```

The scale architecture requires:

```text
stateless workers where practical
persistent state
event-driven communication
async observability
bounded concurrency
rate limiting
timeouts
retries
failure isolation
caching
cost/latency budgets
load testing
```

The system should remain simple enough for this workload and must not become its own bottleneck.

---

# 50. Data Requirements

The data workstream explicitly targets:

```text
200–300 query profiles
500–1,000 model responses
200–300 human-annotated cases
100–200 RAG cases
100–200 intervention cases
50–100 counterfactual cases
50–100 agent trajectories
```

The data must represent:

```text
query
→ profile
→ capabilities
→ initial route
→ execution
→ observations/events
→ failure/uncertainty
→ intervention
→ replan
→ outcome
→ quality/trust/cost/latency
```

---

# 51. Synthetic Enterprise Environment

Use synthetic data.

Recommended logical domains:

```text
customers
employees
products
orders
transactions
revenue
support_tickets
departments
```

Documents:

```text
financial policies
HR policies
security policies
product docs
customer policies
approval policies
technical docs
```

Chat history:

```text
synthetic conversations
```

Target:

```text
5–10 SQL tables
20–50 documents
50–100 synthetic conversations
```

This is sufficient to demonstrate:

```text
SQL
RAG
memory/chat
multi-source routing
```

---

# 52. Canonical Evaluation Scenarios

Build these six first:

## 1. Simple factual

```text
query
→ fast model
→ light verification
→ answer
```

## 2. Enterprise SQL

```text
query
→ SQL
→ deterministic result
→ explanation
→ verify
```

## 3. Insufficient RAG

```text
query
→ RAG
→ insufficient evidence
→ event
→ intervention
→ reretrieve/replan
→ verify
```

## 4. Reasoning escalation

```text
query
→ Qwen3 4B
→ high reasoning uncertainty
→ Grok
→ verifier
→ answer
```

## 5. High-risk agent action

```text
request
→ agent
→ proposed tool action
→ action risk
→ human approval
→ tool
→ verification
```

## 6. Multi-agent lineage failure

```text
Agent A
→ Agent B
→ sensitive data
→ unexpected destination
→ lineage/drift detection
→ intervention
```

---

# 53. Evaluation Metrics

The entire product must ultimately be evaluated against:

```text
final quality
factuality
grounding
safety
unsafe-action rate
recovery rate
false intervention
cost
latency
number of model calls
number of tool calls
```

The system-level question is:

> **Did ControlPlane improve the outcome sufficiently to justify its additional control overhead?**

This is explicitly the system-level evaluation criterion in the governance specification.

---

# 54. Baseline vs ControlPlane Experiment

Every major scenario should run in two modes:

```text
BASELINE
   vs
CONTROLPLANE
```

Record:

```text
quality
trust
factuality
grounding
safety
recovery
cost
latency
model calls
tool calls
intervention count
```

For shadow mode:

```text
actual baseline behavior
vs
what ControlPlane would have done
```

---

# 55. Fine-Tuning Policy — Final

## Do not fine-tune now:

```text
Qwen3 1.3B
Qwen3 4B
Grok
Intervention Engine
Replanner
Trust Engine
PII detector
Safety evaluator
Embedding
Reranker
```

## Candidate later fine-tuning:

### First candidate

```text
Judge / RAG / hallucination evaluator
```

because the project already has human-annotated evaluation data and evaluator-specific research precedent.

The model decision record explicitly identifies the judge/evaluator as the most likely first specialization target.

### Second candidate

```text
query/risk classifier
```

### Third candidate

```text
small intervention policy
```

Only after sufficient labeled execution history.

---

# 56. Algorithm Research Plan

Research in this order:

## P0

```text
1. Query intelligence
2. Risk profiling
3. Capability routing
4. Model routing
5. Hybrid retrieval
6. RAG adequacy
7. Factuality/hallucination
8. Response evaluation
9. Reasoning evaluation
10. Safety/action risk
11. Intervention
12. Replanning
13. Trust aggregation
```

## P1

```text
14. Behavioral drift
15. Permission/data lineage
16. Multi-agent composition
17. learned intervention
18. adaptive compute
```

## P2

```text
19. advanced online learning
20. advanced calibration
21. learned trajectory risk
22. adaptive test-time research
```

---

# 57. Research Papers / Concepts to Study

## Routing

```text
RouteLLM
Model Cascading
Learning to Route LLMs with Confidence Tokens
```

Use them mainly for:

```text
model routing
CHANGE_MODEL
INCREASE_COMPUTE
DECREASE_COMPUTE
```

## RAG

```text
RAGAS
ARES
ColBERTv2
RAGTruth
```

Use them for:

```text
retrieval
RAG adequacy
grounding
hallucination
```

## Evaluation

```text
MT-Bench / Chatbot Arena
Prometheus / Prometheus 2
PandaLM
JudgeLM
HelpSteer2
```

Use them for:

```text
LLM judges
rubric evaluation
pairwise comparison
human-calibrated evaluation
```

## Hallucination

```text
SelfCheckGPT
HaluEval
RAGTruth
```

## Agent safety

```text
SafeAgent
InjecAgent
```

Use them for:

```text
trajectory risk
tool safety
prompt injection
runtime action governance
```

---

# 58. Recommended Code Structure

```text
controlplane/
│
├── app/
│   ├── api/
│   ├── orchestrator/
│   ├── planner/
│   ├── decision_engine/
│   ├── intervention/
│   ├── replanner/
│   ├── trust/
│   ├── policy/
│   ├── routing/
│   └── capabilities/
│
├── evaluators/
│   ├── quality/
│   ├── reasoning/
│   ├── factuality/
│   ├── grounding/
│   ├── safety/
│   ├── privacy/
│   ├── bias/
│   ├── drift/
│   ├── action_risk/
│   └── lineage/
│
├── models/
│   ├── providers/
│   ├── registry/
│   └── judge/
│
├── retrieval/
│   ├── ingestion/
│   ├── retrieval/
│   ├── fusion/
│   ├── reranking/
│   └── adequacy/
│
├── mcp/
│   ├── adapters/
│   ├── model/
│   ├── sql/
│   ├── rag/
│   ├── web/
│   └── tools/
│
├── state/
│   ├── postgres/
│   ├── trajectory/
│   ├── ledger/
│   └── redis/
│
├── events/
│
├── dashboard/
│
├── data/
│
├── experiments/
│
└── tests/
```

Do not automatically turn every folder into a microservice.

---

# 59. Implementation Order

## Phase 0 — Contracts

```text
schemas
interfaces
events
state
registry
```

## Phase 1 — Foundation

```text
API
trace IDs
ExecutionState
PostgreSQL
Redis
Event Bus
Execution Graph
Trajectory/Ledger
```

## Phase 2 — Capabilities

```text
Qwen3 1.3B
Qwen3 4B
Grok
SQL
Qdrant/RAG
reranker
basic tool
```

## Phase 3 — Baseline intelligence

```text
Query Intelligence
Risk
Capability Router
Model Router
RAG Adequacy
basic evaluators
```

## Phase 4 — Control loop

```text
Decision Engine
Intervention V0
Replanner V0
Verification
Trust aggregation
Human review
```

## Phase 5 — Demo scenarios

```text
six canonical scenarios
```

## Phase 6 — Evaluation

```text
baseline
vs
ControlPlane
```

## Phase 7 — Research upgrades

Only now consider:

```text
small local classifier
learned router
fine-tuned evaluator
learned intervention policy
advanced adaptive compute
```

---

# 60. Hard Non-Negotiables for the Coding Agent

The coding agent must not:

- create one giant evaluator model
- fine-tune answer models without evidence
- create one local model per evaluator
- let evaluators make final policy decisions
- let MCP become the brain
- hard-code provider logic into the router
- hard-code recovery inside individual tools
- create unrestricted self-healing
- retry until success
- claim rollback without rollback capability
- store hidden chain-of-thought
- treat Qdrant as source of truth
- use Redis as authoritative state
- create unnecessary databases
- create unnecessary microservices
- add Kafka/Kubernetes merely for appearance
- invent benchmark results
- invent performance numbers

---

# 61. Definition of Done

The system is not complete merely because the API returns an answer.

A meaningful ControlPlane prototype must demonstrate:

```text
[ ] Query is profiled
[ ] Risk is assessed
[ ] Capability route selected
[ ] Model route selected
[ ] Execution plan created
[ ] Execution state persisted
[ ] Events emitted
[ ] Trajectory recorded
[ ] Evaluation performed
[ ] Risk/confidence interpreted
[ ] Decision made
[ ] Intervention possible
[ ] Replanning possible
[ ] Post-intervention verification performed
[ ] Trust/evidence returned
[ ] Human approval possible
[ ] Abstention possible
[ ] Dashboard reconstructs the route
[ ] Baseline comparison exists
[ ] Cost/latency measured
[ ] Six canonical scenarios work
```

---

# 62. Final Architecture Decision on the Three Components You Asked About

## Intervention Engine

**V0: deterministic, no fine-tuning.**

```text
hard constraints
→ candidate generation
→ candidate filtering
→ interpretable scoring
→ intervention
→ verification
```

Later learned policy only after enough execution data.

---

## Replanner

**V0: structured/deterministic planner.**

```text
event
+
execution state
+
policy
+
capabilities
+
budget
→ new graph proposal
→ validation
→ new authoritative plan version
```

A strong LLM may assist proposal generation later, but it is never the policy authority.

---

## Trust Engine

**V0: no dedicated trust model.**

```text
evaluator outputs
+
evidence
+
grounding
+
verification
+
risk
+
trajectory
+
policy
→ Trust Report
```

Use categorical/structured trust initially.

Calibrate or learn trust only after human evaluation shows a need.

---

# 63. Final Product Strategy

The final ControlPlane should demonstrate this:

```text
User:
"Analyze our Q4 revenue decline."

                 ↓

ControlPlane:
Understands → enterprise + analytical + financial

                 ↓

Plans:
SQL + documents + reasoning + verification

                 ↓

Executes:
SQL + RAG in parallel

                 ↓

Observes:
RAG evidence incomplete

                 ↓

Decision:
Current plan insufficient

                 ↓

Intervention:
CHANGE_DATA_SOURCE / RETRIEVE_MORE

                 ↓

Replan:
Plan V2

                 ↓

Reasoning:
Qwen3 4B

                 ↓

Verifier:
Prometheus 2

                 ↓

Trust:
HIGH
with evidence and limitations

                 ↓

Final answer

                 ↓

Complete trace:
query
→ plan
→ data
→ models
→ evaluations
→ intervention
→ replan
→ final result
```

That is the product.

Not:

```text
"Here are five scores about your LLM."
```

But:

> **"ControlPlane observed the AI execution, determined that the current path was insufficient, changed the path, verified the new outcome, and can show exactly why it made that decision."**

This is the implementation direction that best preserves all of the current contracts without prematurely committing to sophisticated ML where deterministic mechanisms are sufficient.

---

# 64. Terminology Alignment

The documents listed in §0 were authored independently and have accumulated multiple, non-identical vocabularies for several cross-cutting concepts (verified by full-text audit of the doc set, 2026-08-27). This section does not redesign any component; it declares which existing spelling is canonical going forward, so that new code and new documentation converge instead of adding a further variant. Where a document still uses a non-canonical form, that form is not wrong so much as pre-dating this alignment — update it opportunistically rather than in a single mass edit.

## 64.1 Intervention Vocabulary

**Canonical (16 values):** `KEEP, VERIFY, RETRIEVE_MORE, RERANK, CHANGE_MODEL, INCREASE_COMPUTE, DECREASE_COMPUTE, CHANGE_DATA_SOURCE, REGENERATE, REPAIR, REDACT, ASK_CLARIFICATION, HUMAN_REVIEW, ABSTAIN, BLOCK, ABORT`.

This is the vocabulary defined in `docs/DATA/ANNOTATION_GUIDELINES.md`, used by `docs/DATA/POSTGRES_SCHEMA.md` §6.3 (runtime `interventions.intervention_type`) and §15.5 (`intervention_labels`), by `docs/architecture/FAILURE_AND_RECOVERY.md` §7 ("Intervention Classes"), and restated above in §25. Two documented, deliberate variants exist and are **not** errors:
- Human-annotation records (`annotations.preferred_intervention`) additionally allow `OTHER` in place of `ABORT`, because a human annotator needs an escape hatch a fixed list can't anticipate, whereas a system-emitted decision must always resolve to one of the 16 concrete actions.
- `docs/architecture/EVENT_MODEL.md` §15.26's "examples of intervention type" (`RETRY, REGENERATE, REROUTE, RETRIEVE, CHANGE_RETRIEVAL, CHANGE_MODEL, INCREASE_REASONING, VERIFY, REPAIR, REDACT, ASK_CLARIFICATION, ABSTAIN, ESCALATE, HUMAN_REVIEW, BLOCK, ABORT`) is illustrative payload content for the `INTERVENTION_TRIGGERED` event, not a competing formal enum — when implementing that payload, populate `intervention_type` from the canonical 16-value list above, not from that example list.

Other documents that still enumerate a different intervention list (e.g. `PRODUCT_THESIS_UPDATED.md` §18, `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` §2/§15/§22/§43) should be read as pre-dating this alignment; the canonical 16-value list above governs.

## 64.2 Top-Level Decision Outcome

**Canonical (8 values):** `PASS, MONITOR, INTERVENE, ESCALATE, ABSTAIN, BLOCK, REPLAN, HUMAN_REVIEW` — as defined in `docs/DATA/POSTGRES_SCHEMA.md` §6.2 (`decisions.decision`).

This is the outcome of the Risk × Confidence decision described in §43 above and in `docs/architecture/ControlPlane_High_Level_Architecture_OPTIMAL.md` Layer 19. Narrower or differently-worded decision lists elsewhere (e.g. `ALLOW/MODIFY/HUMAN/BLOCK` for a single agentic tool-call authorization, or `CONTINUE/STOP` for a cascade controller) are **not** competing top-level vocabularies — they are the output of a specific, narrower sub-decision (tool authorization, cascade continuation) that ultimately feeds into one of the 8 canonical top-level decisions above. Do not treat every local decision point as needing the full 8-value enum, and do not treat the 8-value enum as replacing a narrower sub-decision's own vocabulary.

## 64.3 Severity Scale

**Canonical:** `S0_INFO, S1_LOW, S2_MEDIUM, S3_HIGH, S4_CRITICAL` — as defined in `docs/architecture/FAILURE_AND_RECOVERY.md` §4 (Severity Scale), which is ahead of `EVENT_MODEL.md` in the §0 source-of-truth order.

`docs/architecture/EVENT_MODEL.md`'s event-envelope `severity` field (`info, notice, warning, high, critical`) is a narrower, transport-level field describing how loudly to surface a single event, not a governance judgment about a failure's impact. When an event correlates with an S0–S4 failure, use this rough correspondence: `S0_INFO → info`, `S1_LOW → notice`, `S2_MEDIUM → warning`, `S3_HIGH → high`, `S4_CRITICAL → critical`. This mapping is a convenience default, not a strict 1:1 requirement — an event's transport severity may legitimately be lower than its associated failure's governance severity while awaiting diagnosis.

## 64.4 Model Identifiers

**Canonical prose names:** "Qwen3 ~1.3B" (very-small role), "Qwen3 4B" (medium role), "Grok API" (strong-reasoning role) — as defined in `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md`.

**Canonical machine-readable `model_key` values (for `model_registry.model_key` and dataset JSON):** `qwen3-1.3b`, `qwen3-4b`, `grok`. Use these lowercase-hyphenated forms in code, config, and generated data; reserve the prose forms (with the "~" and "API" qualifiers) for human-readable documentation and dashboards. Other casings found in the doc set (`QWEN3_4B`, `GROK`, `Qwen3 1.3B` without the tilde) predate this alignment.

## 64.5 Query Fingerprint vs. Query Profile

"Query Fingerprint" (`PRODUCT_THESIS_UPDATED.md` §6, `ControlPlane_High_Level_Architecture_OPTIMAL.md` Layer 2) is the product-vision name for the same artifact that the frozen, implemented data schema calls the "Query Profile" (`docs/DATA/SCHEMA.md`, `data/schemas/query_profile.schema.json`, the `query_profiles` / `query_profile` field name used throughout the runtime state and Postgres schema). They are the same concept at two different maturity levels, not two different objects: the Query Profile is the current, narrower, frozen v0.1 implementation of the longer-term Query Fingerprint vision. New work should use the field name `query_profile` and the frozen schema's field set; treat the wider Query Fingerprint dimension list as forward-looking, not yet implemented.

## 64.6 What This Section Does Not Resolve

This alignment intentionally does not attempt to unify every enum found in the doc set — several proliferations reflect genuinely different sub-systems operating at different layers (e.g. the Model Router's `USE_FAST_MODEL/START_CASCADE/...` action vocabulary in `docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md`, the Cascade Controller's `STOP/CONTINUE/...` outputs, and the Intervention Engine budget-field naming variants in `docs/specs/INTERVENTION_ENGINE_IMPLEMENTATION_SPEC.md`). Resolving those requires an engineering decision about whether the sub-systems themselves should be merged, not merely a naming choice, and is out of scope for a documentation pass. Treat any cross-file terminology question not covered by §64.1–§64.5 as open, and resolve it explicitly (with a note in this section) before implementing against conflicting versions.
