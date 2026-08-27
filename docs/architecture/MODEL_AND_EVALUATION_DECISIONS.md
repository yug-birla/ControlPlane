
# ControlPlane.ai — Model & Evaluation Decision Specification

**Status:** Current technical decision record  
**Scope:** Answer-model pool, LLM judge, evaluation datasets, and dataset structure

## 1. Current decisions

### User-facing answer models

| Role | Current decision | Purpose |
|---|---|---|
| Very small | **Qwen3 ~1.3B class** | Low-cost, low-latency/simple queries |
| Medium | **Qwen3 4B** | Medium-complexity queries and normal generation |
| Strong reasoning | **Grok API** | Difficult reasoning / escalation |
| Local Qwen3 8B | **Not used currently** | Deliberately excluded because of local compute/latency trade-off |

The architecture requires model/provider choice to remain an abstraction owned by ControlPlane rather than hard-coded into individual routes. ControlPlane remains responsible for routing, risk, evaluation interpretation, intervention, replanning, trust, and human escalation. fileciteturn0file8L80-L96

### Why no Qwen3 8B?

The current decision is:

```text
Qwen3 ~1.3B
      ↓
Qwen3 4B
      ↓
Grok API
```

The reason is the project's current compute constraint and the desire to use the external strong-reasoning model rather than adding a larger local reasoning model.

The architecture should not automatically escalate every query through every model. The ControlPlane may select a higher tier directly based on query difficulty, risk, policy, latency, cost, and observed model performance.

---

# 2. Answer-model responsibilities

## Qwen3 ~1.3B

Use for:

- simple factual requests
- short summaries
- basic transformations
- simple conversational queries
- low-risk, latency-sensitive workloads

Initial strategy:

```text
pretrained checkpoint
+
prompting
+
routing
```

**No fine-tuning initially.**

---

## Qwen3 4B

Use for:

- medium-complexity queries
- normal RAG generation
- moderate analysis
- simple coding
- multi-step but non-extreme reasoning

Initial strategy:

```text
pretrained checkpoint
+
prompting
+
routing
```

**No fine-tuning initially.**

---

## Grok API

Use for:

- difficult reasoning
- complex synthesis
- high-complexity analysis
- difficult coding/reasoning
- lower-tier model failure
- cases where stronger reasoning is justified

Grok is an escalation capability, not the default model.

The router must consider:

```text
quality requirement
risk
confidence
latency budget
cost budget
model capability
previous failures
```

before escalating.

---

# 3. Judge model

## Current decision

Use:

> **Prometheus 2 — 7B-class evaluator**

The judge is **not** a user-facing answer model.

It provides evaluation signals such as:

- correctness
- relevance
- grounding
- reasoning quality
- rubric-based quality
- pairwise model preference

It can be used in both:

```text
DIRECT EVALUATION
```

and:

```text
PAIRWISE COMPARISON
```

Pairwise evaluation is particularly important for ControlPlane because the router eventually needs to compare candidate model outputs.

LLM-as-a-Judge research also shows that judges can have systematic biases, so judge outputs must be validated rather than treated as ground truth. citeturn0file15

---

# 4. Judge strategy

## Phase 1 — Few-shot prompting

Start with:

```text
Prometheus 2
+
explicit evaluation rubric
+
few-shot examples
```

Do **not** fine-tune immediately.

The first experiment must answer:

> Is the pretrained judge plus a well-designed rubric sufficiently reliable for our ControlPlane use cases?

---

## Phase 2 — Human validation

Compare:

```text
Prometheus judgment
vs.
human judgment
```

Measure agreement separately for:

```text
correctness
relevance
completeness
grounding
reasoning
safety
privacy
intervention correctness
```

Do not use only a single overall agreement number.

---

## Phase 3 — Fine-tuning decision

Only fine-tune if there is evidence that few-shot prompting is insufficient.

Decision rule:

```text
Judge reliable
→ DO NOT FINE-TUNE

Judge has systematic ControlPlane-specific failures
→ build specialized training data
→ fine-tune a smaller/specialized evaluator
```

The fine-tuned model, if eventually needed, should target evaluation rather than generation.

---

# 5. Public datasets for judge development

Use public data before building everything from scratch.

## A. Prometheus 2 evaluation data

Inspect the public feedback and preference data associated with Prometheus 2.

Useful forms:

```text
input
+
response
+
rubric
+
judgment
```

and:

```text
input
+
response A
+
response B
+
preference
```

This is directly relevant to both evaluation and model comparison.

---

## B. HelpSteer2

Useful for multidimensional response evaluation.

Relevant dimensions include:

```text
helpfulness
correctness
coherence
complexity
verbosity
```

Use it to avoid reducing every evaluation to a single score.

---

## C. FLASK

Useful as a reference for fine-grained skill-level evaluation.

Relevant dimensions include:

```text
factuality
logical thinking
completeness
conciseness
readability
harmlessness
```

---

## D. PandaLM

Useful for pairwise model comparison:

```text
query
+
response A
+
response B
+
preferred response
```

This is directly relevant to routing/cascade experiments.

---

## E. JudgeLM

Useful as a research reference for fine-tuning open judge models and understanding judge-specific data generation and bias.

---

# 6. RAG-specific public data

Generic judge data is insufficient for RAG.

Use:

## RAGTruth

For:

- hallucination
- grounding
- claim-level analysis

## ARES

For:

- context relevance
- answer faithfulness
- answer relevance

ARES is particularly relevant because it also demonstrates lightweight judge training/calibration with a relatively small human-annotated set.

## RAGAS

Use as an evaluation framework/reference for:

- context relevance
- faithfulness
- answer relevance

These should be components of the evaluation layer, not the complete ControlPlane.

---

# 7. Factuality / hallucination datasets

Also investigate:

## HaluEval

Useful for hallucination recognition.

## SelfCheckGPT

Useful for understanding black-box hallucination detection through consistency/disagreement among multiple generated samples.

Do not automatically adopt these methods; use them as research candidates and baselines.

---

# 8. ControlPlane-specific dataset

Public datasets will not fully cover the central ControlPlane question:

> **Was the ControlPlane decision itself correct?**

Therefore create a smaller custom dataset.

Initial planning targets from the project data specification are:

```text
200–300 human-annotated cases
100–200 RAG cases
100–200 intervention cases
50–100 counterfactual cases
50–100 agent trajectories
```

These are planning targets, not quotas. fileciteturn7file13L121-L178

The overall dataset must capture:

```text
query
→ query profile
→ required capabilities
→ initial route
→ execution
→ event/failure
→ intervention
→ replan
→ final outcome
→ quality
→ trust
→ cost
→ latency
```

This matches the project's data strategy rather than a simple question/answer dataset. fileciteturn7file13L8-L47

---

# 9. Dataset schema — direct response evaluation

Recommended structure:

```json
{
  "case_id": "resp_001",
  "query": "...",
  "query_profile": {
    "intent": "...",
    "complexity": "...",
    "risk": "..."
  },
  "response": "...",
  "context": ["..."],
  "ground_truth": "...",
  "evaluation": {
    "correctness": 4,
    "relevance": 5,
    "completeness": 4,
    "reasoning": 4,
    "safety": 5,
    "privacy": 5
  },
  "label_source": "HUMAN"
}
```

---

# 10. Dataset schema — pairwise model comparison

This is especially important for model routing.

```json
{
  "case_id": "pair_001",
  "query": "...",
  "response_a": {
    "model": "qwen3-1.3b",
    "answer": "...",
    "latency_ms": 320,
    "estimated_cost": 0.1
  },
  "response_b": {
    "model": "qwen3-4b",
    "answer": "...",
    "latency_ms": 750,
    "estimated_cost": 0.4
  },
  "preference": "B",
  "reason": "...",
  "constraints": {
    "min_quality": 4,
    "max_latency_ms": 1000
  },
  "label_source": "HUMAN"
}
```

The important addition is preserving **cost and latency**, because a router should not learn only:

```text
better answer → winner
```

It should learn:

```text
best answer under constraints → winner
```

---

# 11. Dataset schema — RAG evaluation

```json
{
  "case_id": "rag_001",
  "query": "...",
  "documents": [
    {
      "document_id": "doc_1",
      "text": "..."
    }
  ],
  "retrieved_documents": ["doc_1", "doc_7"],
  "response": "...",
  "labels": {
    "retrieval_quality": "PARTIAL",
    "evidence_sufficiency": "INSUFFICIENT",
    "grounding": "PARTIAL",
    "faithfulness": "LOW"
  },
  "expected_intervention": "RETRIEVE_MORE",
  "label_source": "HUMAN"
}
```

The important distinction is:

```text
retrieval returned documents
```

versus:

```text
retrieval returned sufficient evidence
```

---

# 12. Dataset schema — intervention evaluation

```json
{
  "case_id": "intervention_001",
  "query": "...",
  "initial_route": "RAG",
  "initial_response": "...",
  "failure": "INSUFFICIENT_RAG",
  "risk": "MEDIUM",
  "confidence": "LOW",
  "available_interventions": [
    "RETRIEVE_MORE",
    "CHANGE_MODEL",
    "ASK_CLARIFICATION",
    "ABSTAIN"
  ],
  "expected_intervention": "RETRIEVE_MORE",
  "reason": "...",
  "label_source": "HUMAN"
}
```

This is one of the most important ControlPlane-specific datasets.

---

# 13. Dataset schema — recovery / self-healing

```json
{
  "case_id": "recovery_001",
  "query": "...",
  "initial_execution": {
    "route": "QWEN3_4B",
    "response": "..."
  },
  "failure": "REASONING_FAILURE",
  "intervention": "CHANGE_MODEL",
  "recovery_execution": {
    "route": "GROK",
    "response": "..."
  },
  "evaluation": {
    "before_quality": 2,
    "after_quality": 5,
    "before_grounding": 3,
    "after_grounding": 5
  },
  "recovery_outcome": "IMPROVED",
  "cost_before": "...",
  "cost_after": "...",
  "latency_before": "...",
  "latency_after": "..."
}
```

This evaluates whether the intervention actually improved the result rather than merely changing the route.

---

# 14. Dataset schema — agent trajectory

```json
{
  "trajectory_id": "traj_001",
  "user_request": "...",
  "steps": [
    {
      "step": 1,
      "agent": "A",
      "action": "..."
    },
    {
      "step": 2,
      "tool": "CRM",
      "action": "..."
    }
  ],
  "permissions": ["..."],
  "data_accessed": ["..."],
  "external_destinations": ["..."],
  "risk": "HIGH",
  "drift": "HIGH",
  "intervention_point": 3,
  "expected_control_action": "HUMAN_REVIEW",
  "label_source": "HUMAN"
}
```

This is aligned with the trajectory-level architecture: ControlPlane governs the complete trajectory rather than only the final response. fileciteturn0file6L10-L32

---

# 15. Dataset schema — counterfactual routing

```json
{
  "case_id": "counter_001",
  "query": "...",
  "route_a": {
    "model": "qwen3-1.3b",
    "quality": 3,
    "latency_ms": 250,
    "cost": 1
  },
  "route_b": {
    "model": "qwen3-4b",
    "quality": 5,
    "latency_ms": 700,
    "cost": 3
  },
  "constraints": {
    "min_quality": 3,
    "max_latency_ms": 500,
    "max_cost": 2
  },
  "expected_route": "A"
}
```

This tests whether the router can reason about **quality/cost/latency constraints** rather than automatically choosing the strongest model.

---

# 16. Label provenance

Every evaluation label must record:

```text
HUMAN
EXPERT
LLM_JUDGE
AUTOMATIC
SYNTHETIC
DERIVED
```

Never treat an LLM-generated label as automatically equivalent to human ground truth.

---

# 17. Human annotation strategy

Start with:

```text
200–300 deeply annotated cases
```

Double-annotate at least:

```text
20%
```

For example:

```text
250 total
×
20%
=
50 double-annotated
```

Measure:

```text
human-human agreement
judge-human agreement
```

If disagreement is high:

```text
revise rubric
→ revise examples
→ re-annotate
```

before fine-tuning.

---

# 18. Synthetic data strategy

Do not create the entire judge dataset synthetically.

Use a hybrid:

```text
public human-annotated data
+
your human ControlPlane data
+
synthetic augmentation
```

Synthetic data is especially useful for rare cases:

```text
insufficient RAG
model disagreement
wrong route
unsafe action
permission laundering
partial execution
wrong intervention
recovery failure
```

But high-value ground truth should remain anchored to human/expert annotation.

---

# 19. What the judge should output

Do not reduce the evaluator to:

```text
7.5 / 10
```

Use structured evaluation.

Example:

```json
{
  "correctness": 0.0,
  "relevance": 0.0,
  "grounding": 0.0,
  "reasoning": 0.0,
  "safety": 0.0,
  "privacy": 0.0,
  "confidence": 0.0,
  "issues": ["..."],
  "evidence": ["..."]
}
```

For pairwise comparison:

```json
{
  "winner": "A",
  "confidence": 0.0,
  "reason": "..."
}
```

For ControlPlane-specific evaluation:

```json
{
  "failure_detected": true,
  "failure_type": "RETRIEVAL_INSUFFICIENT",
  "recommended_intervention": "RETRIEVE_MORE"
}
```

The downstream ControlPlane Decision Engine remains responsible for the final action.

---

# 20. Final current model architecture

```text
                    USER QUERY
                        │
                        ▼
                 CONTROLPLANE
                        │
                  MODEL ROUTER
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     Qwen3 ~1.3B    Qwen3 4B       Grok API
      Very Small     Medium       Strong Reasoning
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                 Prometheus 2
                     Judge
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
          quality    grounding   safety
              │         │         │
              └─────────┼─────────┘
                        ▼
                ControlPlane Core
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
       ACCEPT         REPLAN       HUMAN/BLOCK
```

The user-facing answer models and the judge are intentionally separate roles.

---

# 21. Fine-tuning policy

The project should follow this policy:

```text
Pretrained model
      ↓
Few-shot prompting
      ↓
Human validation
      ↓
Measure reliability
      ↓
Identify systematic weakness
      ↓
Only then consider fine-tuning
```

Fine-tuning is **not a mandatory requirement**.

The first likely candidate for specialization is the judge/evaluator because the project already plans human-annotated evaluation data and because evaluator-specific research such as ARES and Prometheus provides precedent.

Do not fine-tune the answer models merely because local compute is available.

---

# 22. Research papers / projects to study first

## Routing / Cascade

1. **RouteLLM — Learning to Route LLMs from Preference Data**
2. **Model Cascading — Towards Jointly Improving Efficiency and Accuracy of NLP Systems**
3. **Learning to Route LLMs with Confidence Tokens**

## Evaluation / Judge

4. **Prometheus / Prometheus 2**
5. **MT-Bench / Chatbot Arena**
6. **PandaLM**
7. **JudgeLM**
8. **HelpSteer2**

## RAG

9. **RAGAS**
10. **ARES**
11. **RAGTruth**
12. **HaluEval**

## Hallucination

13. **SelfCheckGPT**

## Agent safety

14. **SafeAgent**
15. **InjecAgent**

## Retrieval

16. **ColBERTv2**

These should be treated as research candidates. They do not automatically become the final implementation.

---

# 23. What is intentionally NOT decided yet

The following remain open until experiments:

```text
exact routing algorithm
exact query classifier
exact risk model
exact intervention policy
exact RAG sufficiency algorithm
exact hallucination detector
exact trust/calibration method
exact judge fine-tuning strategy
exact queue/event technology
exact database implementation
```

The architecture intentionally keeps these components replaceable.

The runtime specification explicitly says that it defines lifecycle and decision points without selecting specific ML algorithms, model families, retrieval algorithms, risk formulas, or event-bus technologies. fileciteturn0file3L3-L9

---

# 24. Final decision

For the current stage:

```text
ANSWER MODELS

Qwen3 ~1.3B
Qwen3 4B
Grok API


JUDGE

Prometheus 2 7B-class


JUDGE STRATEGY

Few-shot first
→ human validation
→ fine-tune only if necessary


PUBLIC DATA

Prometheus 2 evaluation/preference data
HelpSteer2
FLASK
PandaLM
JudgeLM
RAGTruth
ARES-related RAG evaluation data
HaluEval


CUSTOM DATA

200–300 human-annotated cases
100–200 RAG cases
100–200 intervention cases
50–100 counterfactual cases
50–100 agent trajectories
```

The goal is not to build the largest model stack.

The goal is to prove:

```text
MODEL GENERATION
       ↓
EVALUATION
       ↓
CONTROLPLANE DECISION
       ↓
REROUTE / REPLAN / VERIFY
       ↓
BETTER TRUSTWORTHY OUTCOME
```

This keeps the answer-generation layer, evaluation layer, and ControlPlane decision layer architecturally distinct.
