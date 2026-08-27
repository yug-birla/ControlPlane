# ControlPlane.ai — Routing System & Risk/Capability/Model Router Specification

## Purpose

This document defines the concrete technical requirements for the three most latency-sensitive intelligence components in ControlPlane:

1. **Risk Profiler**
2. **Capability Router**
3. **Model Router**

It also defines:

- routing and cascading
- confidence estimation
- adaptive test-time compute
- model/provider requirements
- small local model requirements
- fine-tuning requirements
- training/evaluation data schemas
- cost/latency optimization
- model registry requirements
- router state
- experiments and baselines
- prototype vs later versions

This is an **implementation specification**, not a claim that every proposed algorithm has already been selected.

The coding agent must treat all algorithm choices as replaceable behind stable interfaces.

---

# 1. Executive Decision

## Recommended initial architecture

Do **not** place an LLM call in every control-plane decision.

The first implementation should target:

```text
USER QUERY
   ↓
Small Query-Intelligence Component
   ↓
Risk + Intent + Capability + Complexity
   ↓
Capability Router
   ↓
Model Router
   ↓
FAST / STRONG / CASCADE
   ↓
Execution
   ↓
Confidence / Evaluation
   ↓
STOP or CONTINUE
   ↓
Verification when required
```

The key optimization is:

> **Risk profiling and capability routing should be cheaper and faster than the model they are deciding whether to call.**

The router itself must not cost more latency/cost than the expected benefit of routing.

---

# 2. Recommended Prototype Inventory

These are **recommended engineering targets**, not hard requirements stated by the competition.

| Component | Initial quantity |
|---|---:|
| Fast generation model role | 1 |
| Strong reasoning generation model role | 1 |
| Independent evaluator/verifier role | 1 |
| Small local query-intelligence model | 0 initially; 1 recommended after baseline |
| Embedding model | 1 |
| Reranker | 1 |
| Risk rules/policy engine | 1 |
| Capability router | 1 |
| Model router | 1 |
| Cascade controller | 1 |
| Confidence aggregator | 1 |
| Model registry | 1 |
| Route registry | 1 |
| Cost/latency monitor | 1 |
| Intervention interface | 1 |
| Replanner interface | 1 |

Do **not** create one separate LLM for every evaluator.

---

# 3. Core Principle: Minimize Control-Plane Calls

Bad architecture:

```text
Query
 ↓
LLM risk classifier
 ↓
LLM capability classifier
 ↓
LLM model router
 ↓
LLM
```

This adds three model calls before useful work begins.

Preferred architecture:

```text
Query
 ↓
ONE cheap query-intelligence inference
 ├── intent
 ├── capability
 ├── complexity
 ├── actionability
 └── sensitivity
        ↓
deterministic policy/risk
        ↓
small router
        ↓
actual model
```

Potentially:

```text
query-intelligence inference
+
rules
+
model registry
+
router features
```

should be sufficient for most requests.

---

# 4. Component A — Risk Profiler

## 4.1 Purpose

Answer:

> **How risky is this request and what kind of risk does it contain?**

The profiler should produce a **risk vector**, not a single generic risk label.

Recommended dimensions:

```text
factuality_risk
reasoning_risk
privacy_risk
pii_risk
security_risk
bias_risk
financial_risk
action_risk
reputational_risk
compliance_risk
```

Also:

```text
impact
actionability
sensitivity
confidence
```

---

# 5. Risk Profiler Architecture

Use three levels.

```text
             QUERY
               ↓
      ┌─────────────────┐
      │ R0: RULES       │
      └────────┬────────┘
               ↓
       obvious risk?
        /           \
      yes             no/uncertain
       │                   │
       ▼                   ▼
   risk result      R1: small classifier
                           ↓
                       uncertain?
                         /   \
                       no     yes
                        │       │
                        ▼       ▼
                    result   R2: deeper
                              risk analysis
```

## R0 — deterministic risk signals

Use:

- PII pattern detection
- sensitive-field detection
- financial/action verbs
- destructive-action verbs
- regulated-domain indicators
- tool/action indicators
- explicit high-impact targets
- application policy

Examples:

```text
"Delete production database records"
→ action = critical

"Show me all customer Aadhaar numbers"
→ privacy = critical, PII = critical

"Summarize this document"
→ generally low action risk
```

R0 should be extremely fast.

---

# 6. R1 — Small Risk Classifier

A small local classifier is **recommended only after a baseline exists**.

Possible architecture:

```text
query
 ↓
embedding / compact encoder
 ↓
multi-label classifier
 ↓
risk vector
```

Candidate model families for experimentation:

```text
MiniLM
DistilBERT
DeBERTa
other compact encoder models
```

Do not assume one is best.

Benchmark:

```text
precision
recall
F1
high-risk false-negative rate
calibration
latency
CPU/GPU memory
```

## Fine-tuning

Fine-tuning is **optional initially**.

Use:

```text
pretrained encoder
```

first.

Fine-tune when the internal annotation set is large and consistent enough to show that the pretrained model is insufficient.

---

# 7. R2 — Deep Risk Escalation

Only use deeper analysis for:

- critical actions
- ambiguous requests
- unknown risk classes
- conflicting signals
- high-impact domains
- low-confidence classification

The deeper mechanism can be:

```text
strong evaluator LLM
```

or a richer policy/evidence evaluation.

It should NOT be the default path.

---

# 8. Risk Output Contract

Recommended conceptual output:

```json
{
  "risk_vector": {
    "factuality": 0.0,
    "reasoning": 0.0,
    "privacy": 0.0,
    "pii": 0.0,
    "security": 0.0,
    "bias": 0.0,
    "financial": 0.0,
    "action": 0.0
  },
  "impact": "low|medium|high|critical",
  "actionability": "none|draft|decision|external_action",
  "sensitivity": "public|internal|sensitive|restricted",
  "confidence": 0.0,
  "requires_deep_control": false
}
```

The numbers are examples only.

Do not invent calibrated probabilities without calibration experiments.

---

# 9. Risk Profiler: Latency Requirement

The risk profiler is part of the critical path.

Therefore:

```text
P95 risk-profiling latency
must be significantly lower than
P95 generation latency
```

Do not set a numeric threshold before benchmarking.

Measure:

```text
p50
p95
p99
```

for:

```text
rules only
rules + local classifier
rules + local classifier + deep escalation
```

Then select the cheapest configuration that provides acceptable high-risk recall.

---

# 10. Component B — Capability Router

## 10.1 Purpose

Answer:

> **What capabilities are required to solve this query?**

This is different from model routing.

Possible capabilities:

```text
GENERAL_LLM
REASONING
SQL
RAG
WEB
CHAT_HISTORY
MEMORY
CODING
AGENT
VERIFICATION
HUMAN_REVIEW
```

A query can require multiple capabilities.

Example:

```text
"Should we acquire company X?"

→ WEB
→ ENTERPRISE_DATA
→ REASONING
→ VERIFICATION
```

---

# 11. Capability Router Architecture

Preferred first version:

```text
query
 ↓
shared query-intelligence representation
 ↓
multi-label capability classifier
 ↓
candidate capabilities
 ↓
policy filtering
```

Do NOT use another large LLM by default.

---

# 12. Shared Query-Intelligence Model

A strong optimization is to use one compact model with multiple heads:

```text
                     QUERY
                       ↓
               Shared Encoder
                       │
       ┌───────────────┼────────────────┐
       ↓               ↓                ↓
     Intent        Capability       Complexity
       ↓               ↓                ↓
    output           output          output
                       │
               Sensitivity/Impact
```

Potential heads:

```text
intent
capability
complexity
sensitivity
actionability
```

The same representation can feed risk features.

This avoids:

```text
5 separate inference calls
```

and can become:

```text
1 local inference
→ multiple decisions
```

---

# 13. Capability Router Training Data

Recommended row:

```json
{
  "query_id": "q_001",
  "query": "...",
  "intent": ["analytical", "decision_support"],
  "capabilities": ["sql", "rag", "reasoning"],
  "complexity": "high",
  "sensitivity": "internal",
  "actionability": "decision",
  "risk_labels": ["financial", "reasoning"],
  "expected_initial_route": "sql+rags+reasoning"
}
```

Minimum initial target:

```text
200–300 query profiles
```

from the project data workstream.

Do not randomly distribute them. Ensure route/category coverage.

---

# 14. Capability Router Training Strategy

## Version 0

```text
rules + taxonomy
```

## Version 1

```text
pretrained compact encoder
+
classifier heads
```

## Version 2

```text
fine-tune on project-specific query profiles
```

The capability router should remain lightweight.

---

# 15. Capability Router Latency Strategy

Do not use:

```text
LLM → capability decision
```

for every query.

Prefer:

```text
one compact query-intelligence inference
```

and cache safe repeated classifications where appropriate.

Because capability routing only determines the tool/data/model family, it does not require the expressive power of a frontier reasoning model.

---

# 16. Component C — Model Router

This is the most sophisticated of the three.

The Model Router must answer:

> **Given the current state and constraints, what should happen next?**

It must account for:

```text
query
intent
required capability
risk
confidence
quality target
predicted score
latency budget
cost budget
current route
current model
remaining budget
previous failures
trajectory state
evidence quality
model availability
historical model performance
policy
```

---

# 17. Model Router Should Not Be Just a Classifier

This is important.

Do NOT define:

```text
query → model
```

Define:

```text
STATE
→ ACTION
```

Possible actions:

```text
USE_FAST_MODEL
USE_STRONG_MODEL
START_CASCADE
CONTINUE_CURRENT_MODEL
SWITCH_MODEL
INCREASE_COMPUTE
DECREASE_COMPUTE
RUN_PARALLEL
VERIFY
HUMAN_REVIEW
ABSTAIN
```

This makes the router a **runtime policy**, not just a model classifier.

---

# 18. Model Registry

Create a model registry.

Each model record should contain:

```text
model_id
provider
version
capabilities

estimated_quality_by_task
observed_quality_by_task

estimated_latency
observed_p50_latency
observed_p95_latency

input_cost
output_cost

context_limit
tool_support
reasoning_support

availability
health_status
```

Observed values must come from benchmarks.

Estimated values may be initialized manually but must be marked as estimates.

---

# 19. Model Choices

Do not hard-code one provider as permanently "best."

Benchmark at least:

## Cost/latency candidates

### Gemini 2.5 Flash-Lite

Google currently lists Gemini 2.5 Flash-Lite at approximately:

```text
$0.10 / 1M input tokens
$0.40 / 1M output tokens
```

on the standard paid tier. Google describes it as optimized for cost-efficient high-scale use. citeturn154093search0

This makes it a strong candidate for:

```text
fast path
simple query
low-risk generation
cheap probe
high-volume workloads
```

### GPT-5 mini

OpenAI currently lists GPT-5 mini at:

```text
$0.25 / 1M input
$2.00 / 1M output
```

and positions it for cost-sensitive, low-latency, high-volume workloads. citeturn154093search1

Strong candidate for:

```text
general fast model
router-assisted generation
cheap reasoning-capable path
```

## Strong-model candidate

### Claude Sonnet 5

Anthropic currently lists Claude Sonnet 5 at:

```text
$2 / 1M input
$10 / 1M output
```

and positions it as a high-capability model. citeturn154093search2

Use only when the expected quality benefit justifies the higher cost/latency.

## Additional candidate

### GPT-5

OpenAI currently lists GPT-5 at approximately:

```text
$1.25 / 1M input
$10 / 1M output
```

and supports reasoning, tool use and structured outputs. citeturn154093search3

It should be benchmarked as another strong-model option.

### Important

Prices change.

The router must therefore use a configurable model registry rather than hard-coded economic assumptions.

---

# 20. Recommended Prototype Model Portfolio

Start with:

```text
FAST:
Gemini 2.5 Flash-Lite
or GPT-5 mini

STRONG:
Claude Sonnet 5
or GPT-5

VERIFIER:
A separate evaluator configuration/model
```

Do not necessarily deploy all four simultaneously.

Benchmark:

```text
Gemini Flash-Lite
GPT-5 mini
GPT-5
Claude Sonnet 5
```

on the actual workload.

Then choose a fast/strong pair based on:

```text
quality
latency
cost
reliability
tool support
```

This is a benchmark decision, not a permanent product decision.

---

# 21. Do Not Use API Price Alone

The cheapest token price is not automatically the cheapest route.

Define:

```text
effective_route_cost =
model_cost
+ retrieval_cost
+ verifier_cost
+ reranker_cost
+ tool_cost
+ expected_retry_cost
```

Likewise:

```text
effective_latency =
critical_path_model_latency
+
retrieval_latency
+
reranker_latency
+
verification_latency
+
queue_wait
```

If steps run in parallel, use the actual critical path rather than summing all durations.

---

# 22. Router Objective

The router should optimize subject to constraints.

Conceptually:

```text
maximize:
    expected quality
    + risk reduction
    + confidence improvement

subject to:
    cost ≤ budget
    latency ≤ budget
    policy constraints
    risk ≤ allowed threshold
```

An alternative utility formulation can be experimented with:

```text
utility =
quality_value
- λ_cost * cost
- λ_latency * latency
- λ_risk * residual_risk
```

Do not hard-code this as the final objective until experiments establish suitable weights.

The first baseline may be threshold-based.

---

# 23. Model Router Feature Set

The router should receive at least:

```text
query_embedding

intent
capability
complexity

risk_vector
impact
actionability

current_route
current_model
current_plan_version

confidence
evidence_quality
model_disagreement

remaining_cost_budget
remaining_latency_budget
remaining_model_call_budget
remaining_replan_budget

candidate_model_features:
  predicted_quality
  predicted_latency
  predicted_cost
  task capability

historical performance:
  task-level quality
  recent failure rate
```

This is the required state-aware router.

---

# 24. "Current Route" Must Be a First-Class Feature

Example:

```text
Current route:
RAG → Fast Model
```

Then:

```text
retrieval = sufficient
fast confidence = low
latency budget = available
```

The router should prefer:

```text
RAG → Strong Model
```

instead of restarting from the beginning.

The architecture already defines mutable plan versions and runtime replanning. The router must therefore be state-aware rather than stateless. 

---

# 25. Confidence System

Do not use only one confidence number.

Maintain:

```text
model_confidence
evidence_confidence
routing_confidence
verification_confidence
```

For example:

```text
model_confidence = HIGH
evidence_confidence = LOW
```

should not yield:

```text
trust = HIGH
```

The confidence layer must be explicit about its source.

---

# 26. Confidence Sources

Possible sources:

### C1 — Model self-confidence

Useful but not inherently trustworthy.

### C2 — External evaluator

Useful for stronger validation.

### C3 — Evidence support

Often critical for RAG.

### C4 — Model disagreement

Multiple model outputs disagreeing can be a warning.

### C5 — Historical calibration

How often does this model succeed on similar cases?

### C6 — Verification outcome

Deterministic/structured verification when possible.

Combine these rather than blindly trusting one signal.

---

# 27. Self-REF / "Self-GPT" Direction

If by "Self-GPT" you mean the confidence-token approach you discussed, treat it as the **Self-REF research direction**.

Self-REF studies fine-tuning a local model to emit confidence tokens that can support routing/rejection decisions.

Use it as:

```text
Fast Local Model
 ↓
answer + confidence token
 ↓
cascade decision
```

not necessarily:

```text
Model A
+
separate confidence LLM B
```

This can reduce latency because the model itself produces the confidence signal.

However, Self-REF requires a fine-tuned local model, so it should be a later experiment rather than the initial dependency.

---

# 28. Self-REF Data Structure

For each training example:

```json
{
  "query": "...",
  "ground_truth": "...",
  "model_response": "...",
  "is_correct": true,
  "confidence_label": "HIGH"
}
```

For more granular research:

```json
{
  "query": "...",
  "response": "...",
  "task_type": "reasoning",
  "correct": false,
  "difficulty": "hard",
  "confidence_target": "LOW",
  "verification_signal": "...",
  "token_budget": 512
}
```

The exact Self-REF labeling scheme must be taken from the paper implementation before training; do not invent paper-specific token IDs.

---

# 29. Routing + Cascading

Use both.

## Routing

Decision before execution:

```text
query
→ initial route
```

## Cascading

Decision after partial execution:

```text
cheap model
 ↓
confidence/evaluation
 ↓
good enough?
 ├── YES → STOP
 └── NO → stronger model / more compute
```

This is the recommended architecture.

---

# 30. Cascade Controller

The cascade controller should have only one core question:

> **Is additional computation expected to improve the outcome enough to justify its cost/latency?**

Inputs:

```text
current quality estimate
confidence
risk
evidence
remaining budget
current model
candidate next model
expected improvement
expected incremental cost
expected incremental latency
```

Outputs:

```text
STOP
CONTINUE
SWITCH_MODEL
VERIFY
ABSTAIN
```

---

# 31. Does Cascading Require Another Model?

**Not necessarily.**

Initial cascade can use:

```text
Fast model
+
existing confidence/evaluation signal
```

For example:

```text
Fast model
 ↓
self/evaluator confidence
 ↓
threshold
```

Only if confidence is insufficient:

```text
Strong model
```

An optional later version can use a dedicated cascade decision model.

Do not add another LLM merely to decide whether to call another LLM.

---

# 32. Cascade Confidence Thresholds

Do not hard-code:

```text
confidence > 0.8 → stop
```

until calibrated.

Instead learn the threshold using a validation dataset.

For each confidence threshold:

```text
threshold
→ accuracy
→ cost
→ latency
→ escalation rate
```

select a Pareto-efficient operating point.

---

# 33. Adaptive Test-Time Compute

Your uploaded adaptive-compute research is relevant here.

It studies:

```text
STOP
SEQUENTIAL
PARALLEL
```

after a cheap probe. The research report notes that the second routing decision—sequential versus parallel continuation—can be a bottleneck, motivating hierarchical routing. fileciteturn0file17L33-L53

For ControlPlane:

```text
FAST/PROBE
     ↓
confidence/difficulty
     ↓
┌─────────┬────────────┐
STOP   SEQUENTIAL    PARALLEL
```

Use this as a **future P1/P2 routing experiment**, not as a mandatory first implementation.

---

# 34. Parallel Cascade

Use parallel reasoning only when:

```text
ambiguity is high
expected improvement is high
latency budget permits
```

Otherwise use sequential continuation.

Possible policy:

```text
low uncertainty
→ STOP

moderate uncertainty
→ SEQUENTIAL

high uncertainty + independent reasoning useful
→ PARALLEL
```

The exact policy must be learned/tested.

---

# 35. Routing Dataset

You need a dedicated **Model Routing Dataset**.

Recommended row:

```json
{
  "query_id": "q_001",
  "query": "...",
  "task_type": "reasoning",
  "risk_profile": {...},
  "capability": ["reasoning"],

  "current_route": "fast_generation",

  "candidates": [
    {
      "model": "fast_model",
      "quality": 0.81,
      "confidence": 0.78,
      "latency_ms": 240,
      "cost": 0.001
    },
    {
      "model": "strong_model",
      "quality": 0.95,
      "confidence": 0.92,
      "latency_ms": 1200,
      "cost": 0.01
    }
  ],

  "budgets": {
    "max_latency_ms": 1500,
    "max_cost": 0.02
  },

  "preferred_action": "strong_model"
}
```

The actual values should come from measurements.

---

# 36. Pairwise Preference Data

Also create:

```json
{
  "query_id": "q_001",
  "model_a": "fast_model",
  "model_b": "strong_model",
  "response_a": "...",
  "response_b": "...",
  "winner": "model_b",
  "reason": "more correct reasoning",
  "human_validated": true
}
```

This is directly useful for RouteLLM-style training.

---

# 37. Counterfactual Routing Data

You also need:

```json
{
  "query_id": "q_001",
  "route_a": {...},
  "route_b": {...},
  "quality_a": 0.82,
  "quality_b": 0.95,
  "cost_a": 1.0,
  "cost_b": 5.0,
  "latency_a": 300,
  "latency_b": 1400,

  "constraint": {
    "quality_min": 0.80,
    "latency_max_ms": 500
  },

  "preferred_route": "route_a"
}
```

This teaches the router that the best model changes depending on the constraints.

---

# 38. Model Benchmark Dataset

Before training the router, benchmark every candidate model on the same task set.

Store:

```text
query_id
task
model
response
quality
factuality
grounding
reasoning
safety
confidence
latency
input_tokens
output_tokens
cost
failure
```

This becomes your model capability profile.

---

# 39. Training / Validation / Test Split

Never train the router on the same queries used for final evaluation.

Recommended starting split:

```text
60% train
15% validation
15% test
10% challenge
```

For routing, prefer **scenario-level separation** where possible.

Example:

Do not put:

```text
"What was revenue in Q1?"
"What was revenue in Q2?"
```

randomly across train/test if they are generated from identical templates.

---

# 40. Fine-Tuning Strategy for Model Router

Do not fine-tune a large generative model.

Train a small routing policy/model.

Candidates:

```text
gradient-boosted trees
small MLP
compact encoder classifier
matrix-factorization router
RouteLLM-style router
```

Benchmark them.

A tree/MLP router may be faster and easier to explain than an LLM router.

---

# 41. Suggested Router Training Progression

```text
V0
rules + budgets
        ↓
V1
heuristic score
        ↓
V2
small ML router
        ↓
V3
RouteLLM-style preference router
        ↓
V4
state-aware cost/latency router
        ↓
V5
routing + cascade controller
        ↓
V6
confidence-aware adaptive compute
```

Do not implement all versions simultaneously.

---

# 42. Router Scoring Function

The first baseline can use an explicit score.

Conceptually:

```text
route_score =
quality_value
- cost_penalty
- latency_penalty
- risk_penalty
- switch_penalty
```

With constraint gates:

```text
if risk > maximum_allowed:
    reject route

if expected_quality < required_quality:
    reject route

if predicted_latency > remaining_latency_budget:
    reject route

if predicted_cost > remaining_cost_budget:
    reject route
```

Then choose among surviving routes.

This provides a transparent baseline against which learned routing can be compared.

---

# 43. "Current Route" Switching Cost

Include a switching penalty.

For example:

```text
CURRENT:
RAG → Fast

NEW:
restart from Web → Strong
```

may be much more expensive than:

```text
CURRENT:
RAG → Fast

NEW:
continue same RAG evidence → Strong
```

Therefore:

```text
switch_cost
```

should be a router feature.

---

# 44. Remaining Budget Must Be State

Track continuously:

```text
remaining_cost_budget
remaining_latency_budget
remaining_model_call_budget
remaining_tool_budget
remaining_replan_budget
```

The router must make decisions based on **remaining** budget, not the original budget.

Example:

```text
initial cost budget = $0.02

already spent = $0.015

remaining = $0.005
```

The router should not select a model requiring another $0.01.

---

# 45. Cost Must Be Expected Cost

Don't just use direct model price.

For cascading:

```text
expected_cost =
cost_fast
+
P(cascade) × cost_strong
+
P(verify) × cost_verifier
```

Similarly:

```text
expected_latency =
critical_path_fast
+
P(cascade) × incremental_latency
+
P(verify) × verification_latency
```

This is critical for making cascade decisions intelligently.

---

# 46. Example Cascade Decision

Suppose:

```text
Fast:
cost = 1
latency = 200 ms
confidence = 0.91

Strong:
additional cost = 5
additional latency = 1000 ms

Minimum required quality = 0.85
```

If the calibrated confidence signal predicts:

```text
P(fast is sufficient) = 0.97
```

then cascade is probably wasteful.

If:

```text
P(fast is sufficient) = 0.55
```

then escalation is much more attractive.

The actual threshold must be learned from validation data.

---

# 47. Model Router Evaluation Metrics

Do NOT only measure router accuracy.

Measure:

### Quality

```text
final answer quality
```

### Cost

```text
average cost/query
cost per successful answer
```

### Latency

```text
p50
p95
p99
```

### Routing

```text
route accuracy
wrong-route rate
unnecessary escalation
```

### Cascade

```text
stop rate
escalation rate
recovery rate
```

### Risk

```text
high-risk miss rate
unsafe-action miss rate
```

### Efficiency

```text
model calls/query
tokens/query
tool calls/query
```

### Main KPI

The most useful comparison is:

```text
BASELINE
vs
CONTROLPLANE
```

under the same workload.

---

# 48. Pareto Frontier

Do not select a router based on one scalar score only.

Plot:

```text
quality
vs
cost
```

and:

```text
quality
vs
latency
```

Then identify Pareto-efficient policies.

Example:

```text
             Quality
                ↑
                │        ● Strong
                │
                │   ● Router
                │
                │ ● Fast
                └────────────────→ Cost
```

Your goal is not necessarily the absolute strongest model.

Your goal is:

> **Best quality that satisfies the relevant cost/latency/risk constraints.**

---

# 49. Required Data Volume

For the initial project:

```text
Query profiles:
200–300

Model responses:
500–1,000

Human-validated:
200–300

RAG:
100–200

Intervention:
100–200

Counterfactual:
50–100

Agent trajectories:
50–100
```

These targets are from the project data workstream and should be treated as starting targets, not quotas. 

For serious router fine-tuning, you may need substantially more model-comparison examples than the initial human annotation set.

Generate additional model outputs automatically, then human-validate a subset.

---

# 50. Fine-Tuning Data Structure

Maintain separate datasets.

## `query_profiles.jsonl`

```json
{
  "query_id": "...",
  "query": "...",
  "intent": [...],
  "capabilities": [...],
  "complexity": "...",
  "risk": {...},
  "sensitivity": "...",
  "actionability": "..."
}
```

## `model_comparisons.jsonl`

```json
{
  "query_id": "...",
  "model_a": "...",
  "model_b": "...",
  "quality_a": 0.0,
  "quality_b": 0.0,
  "winner": "...",
  "human_validated": true
}
```

## `router_observations.jsonl`

```json
{
  "query_id": "...",
  "state": {...},
  "candidate_routes": [...],
  "budget": {...},
  "outcome": {...},
  "preferred_action": "..."
}
```

## `cascade_cases.jsonl`

```json
{
  "query_id": "...",
  "probe_response": "...",
  "confidence": 0.0,
  "probe_quality": 0.0,
  "additional_compute_action": "STOP|SEQUENTIAL|PARALLEL",
  "final_quality": 0.0,
  "incremental_cost": 0.0,
  "incremental_latency_ms": 0
}
```

## `risk_annotations.jsonl`

```json
{
  "query_id": "...",
  "query": "...",
  "risk_vector": {...},
  "impact": "...",
  "actionability": "...",
  "human_validated": true,
  "label_source": "HUMAN"
}
```

---

# 51. Data Provenance

Every model observation should include:

```text
timestamp
model
provider
model_version
prompt_version
temperature
seed if applicable
input_tokens
output_tokens
latency
cost
```

Every human label should include:

```text
annotator_id
label_source
annotation_version
timestamp
```

Every router decision should include:

```text
router_version
feature_schema_version
policy_version
```

This makes experiments reproducible.

---

# 52. Model Selection Experiment

Before choosing your production pair, run:

```text
same queries
+
same prompts
+
same evaluation
```

against:

```text
Gemini 2.5 Flash-Lite
GPT-5 mini
GPT-5
Claude Sonnet 5
```

or another current candidate set.

Measure:

```text
quality
reasoning
factuality
latency
cost
failure
tool use
```

Do not declare a universal winner.

Choose:

```text
best fast model
best strong model
best verifier
```

for YOUR workload.

---

# 53. Important Cost Caveat

Current published prices are useful for planning, but:

- provider prices can change
- actual latency depends on region, load, networking, batching and provider tier
- token lengths dominate cost
- reasoning tokens can affect output cost
- tool calls add additional cost
- retries/cascades increase effective cost

Therefore the Model Registry must contain both:

```text
published_cost
```

and:

```text
measured_effective_cost
```

Never use published price alone for router decisions.

---

# 54. Latency Strategy

The router must optimize **critical-path latency**, not total compute time only.

Parallel work can reduce critical-path latency:

```text
SQL ──────┐
          ├→ merge → reasoning
RAG ──────┘
```

Total compute increases, but wall-clock time may remain acceptable.

Therefore store:

```text
node_latency
start_time
end_time
dependency_group
critical_path
```

---

# 55. Caching Strategy for Routers

Cache safe deterministic results:

```text
model capability metadata
risk classification for exact repeated public queries
capability classification for repeated benchmark queries
embeddings
retrieval results where freshness permits
```

Do not blindly cache:

```text
personalized risk
private user state
time-sensitive data
agent action authorization
dynamic budget state
```

---

# 56. Recommended Routing Stack

The final recommended architecture is:

```text
                         QUERY
                           │
                           ▼
                ┌────────────────────┐
                │ Shared Query Model │
                │ or lightweight     │
                │ query intelligence │
                └─────────┬──────────┘
                          │
             ┌────────────┼─────────────┐
             ▼            ▼             ▼
          Intent      Capability     Complexity
             │            │             │
             └────────────┼─────────────┘
                          ▼
                   Risk / Policy
                          │
                          ▼
                   Capability Router
                          │
                     candidate routes
                          │
                          ▼
                    MODEL ROUTER
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
           FAST         STRONG      CASCADE
                                      │
                                      ▼
                                    PROBE
                                      │
                                 confidence
                                      │
                             ┌────────┴────────┐
                             ▼                 ▼
                           STOP            CONTINUE
                                               │
                                      ┌────────┴────────┐
                                      ▼                 ▼
                                  SEQUENTIAL         PARALLEL
                                      │                 │
                                      └────────┬────────┘
                                               ▼
                                            VERIFY
                                               │
                                               ▼
                                          OUTCOME
```

---

# 57. What Should Be Local vs API

## Local

Prefer local execution for:

```text
PII detection
basic risk classification
query classification
capability classification
small router
drift scoring
cost calculations
policy rules
```

Reasons:

```text
very low latency
low marginal cost
data privacy
high throughput
```

## API/remote

Prefer API or strong hosted/local-server inference for:

```text
strong reasoning
complex generation
difficult verification
high-quality evaluation
specialist multimodal tasks
```

This is a design pattern, not a mandatory provider choice.

---

# 58. What Should Be Fine-Tuned

## High-priority fine-tuning candidates

```text
1. Query/capability classifier
2. RAG/hallucination evaluator
3. Model router
4. Self-REF confidence model
```

## Low-priority

```text
Risk model
```

only if rules + generic classifier are inadequate.

## Do not fine-tune initially

```text
fast generation model
strong reasoning model
embedding
reranker
general safety model
```

unless experiments show a real bottleneck.

---

# 59. Research Papers to Anchor the Design

## Routing

### RouteLLM
Learning to route between LLMs using preference data.

Use for:

```text
model router baseline
preference data
cost/quality routing
```

https://arxiv.org/abs/2406.18665

### FrugalGPT
Adaptive model cascading for cost/quality control.

Use for:

```text
cascade controller
```

https://arxiv.org/abs/2305.05176

### Model Cascading
Study model cascades for efficiency and accuracy.

Use for:

```text
strong/weak model sequence
```

https://arxiv.org/abs/2210.05528

### Self-REF
Learned confidence tokens for routing/rejection.

Use for:

```text
confidence-aware cascade
```

https://proceedings.mlr.press/v267/chuang25b.html

---

# 60. Research for Evaluation

### RAGAS

Use for:

```text
RAG evaluation
faithfulness
relevance
```

https://arxiv.org/abs/2309.15217

### ARES

Use for:

```text
learned RAG evaluation
human-calibrated evaluation
```

https://arxiv.org/abs/2311.09476

### RAGTruth

Use for:

```text
hallucination detection
RAG annotations
```

https://arxiv.org/abs/2401.00396

### SelfCheckGPT

Use for:

```text
black-box hallucination detection
```

https://arxiv.org/abs/2303.08896

### MT-Bench / Chatbot Arena

Use for:

```text
LLM judge limitations
pairwise evaluation
```

https://arxiv.org/abs/2306.05685

### Prometheus

Use for:

```text
specialized evaluator models
```

https://arxiv.org/abs/2310.08491

---

# 61. Research for Agentic Control

### SafeAgent

Use for:

```text
runtime trajectory governance
agent safety
runtime decision architecture
```

https://arxiv.org/abs/2604.17562

### InjecAgent

Use for:

```text
tool-agent prompt injection
agent safety benchmark
```

https://arxiv.org/abs/2403.02691

---

# 62. Research for Retrieval

### ColBERTv2

Use for:

```text
late-interaction retrieval
reranking
retrieval efficiency
```

https://aclanthology.org/2022.naacl-main.272/

---

# 63. Research for Adaptive Compute

Use the project's existing adaptive-compute research reference.

Its prototype framing is:

```text
probe
→ STOP / SEQUENTIAL / PARALLEL
```

and it explicitly studies learned routing, token efficiency and the gap between learned and oracle routing.

Do not implement this immediately; use it to design the cascade experiments.

---

# 64. Implementation Priority

## P0 — Build first

```text
1. Model Registry
2. Capability Registry
3. Cost/Latency Tracker
4. deterministic Risk/Policy layer
5. lightweight Query/Capability classifier interface
6. heuristic Model Router
7. Fast model
8. Strong model
9. basic verifier
10. basic cascade
```

## P1 — Improve routing

```text
11. small trained query classifier
12. small trained router
13. RouteLLM baseline
14. confidence-aware cascade
15. model disagreement
16. adaptive compute
```

## P2 — Research enhancements

```text
17. Self-REF
18. learned intervention policy
19. online routing
20. advanced adaptive compute
```

---

# 65. Non-Negotiable Router Requirements

The Model Router must:

```text
[ ] Know the current route
[ ] Know the current model
[ ] Know remaining cost budget
[ ] Know remaining latency budget
[ ] Know risk
[ ] Know confidence
[ ] Know required capability
[ ] Know candidate-model cost
[ ] Know candidate-model latency profile
[ ] Know candidate-model quality profile
[ ] Know previous execution failures
[ ] Know whether evidence is sufficient
[ ] Know whether verification is required
[ ] Account for route-switch cost
[ ] Account for expected cascade probability
[ ] Support STOP
[ ] Support CONTINUE
[ ] Support SWITCH
[ ] Support VERIFY
[ ] Support HUMAN_REVIEW
[ ] Support ABSTAIN
[ ] Emit an auditable reason
[ ] Emit estimated cost
[ ] Emit estimated latency
```

---

# 66. Definition of Done for Routing

Do not declare the router complete because it selects a model.

The router is complete only when:

```text
[ ] Risk profile is available
[ ] Capability profile is available
[ ] Model registry exists
[ ] Cost telemetry exists
[ ] Latency telemetry exists
[ ] Current route is tracked
[ ] Remaining budgets are tracked
[ ] Candidate models are benchmarked
[ ] Basic routing baseline exists
[ ] Cascade baseline exists
[ ] Confidence signal exists
[ ] Router decisions are logged
[ ] Router decisions are reproducible
[ ] Quality/cost/latency are evaluated jointly
[ ] Baseline vs router comparison exists
[ ] Worst-case/high-risk routing is tested
[ ] Burst/latency impact is load-tested
```

---

# 67. Final Design Decision

The recommended architecture is NOT:

```text
LLM Risk Agent
→ LLM Capability Agent
→ LLM Router
→ LLM
```

It is:

```text
                CHEAP QUERY INTELLIGENCE
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           RISK       CAPABILITY  COMPLEXITY
              │          │
              └──────────┼──────────┘
                         ▼
                    MODEL ROUTER
                         │
              ┌──────────┼───────────┐
              ▼          ▼           ▼
            FAST       STRONG     CASCADE
                                     │
                                  CONFIDENCE
                                     │
                                STOP / CONTINUE
                                     │
                              SEQUENTIAL/PARALLEL
                                     │
                                  VERIFY
```

The central principle is:

> **Use the least expensive reliable mechanism capable of making each decision, and only spend additional inference when the expected quality/risk benefit justifies the incremental cost and latency.**

This should be the guiding optimization principle for the ControlPlane router.
