# ControlPlane.ai — Final Evaluation & Governance Component Specification

## Purpose

This document freezes the **implementation requirements and decision boundaries** for the following eight ControlPlane components:

1. Response Quality Evaluator
2. Reasoning Evaluator
3. Safety Evaluator
4. Privacy / PII Detector
5. Bias Evaluator
6. Behavioral Drift Monitor
7. Action Risk Evaluator
8. Permission / Data-Lineage Engine

These components sit inside the existing ControlPlane architecture. They are **not independent products, not separate orchestration brains, and not automatically separate services**.

The architecture already establishes that:

- ControlPlane owns evaluation interpretation, intervention, replanning, trust, and human escalation.
- The Execution Graph represents what should happen.
- The Event Bus represents what happened or changed.
- MCP is a capability/interoperability fabric and **must not become the brain**.
- The governed object for agentic execution is the complete trajectory, not only the final response.
- The runtime is deliberately algorithm-agnostic; algorithm selection belongs below these contracts.

This document therefore defines **what each component must do**, what data it needs, what it returns, what the first implementation should be, what should remain optional, and what the coding agent must not invent.

---

# 1. Global Non-Negotiable Rules

## 1.1 No component is the final policy authority

The components below produce **normalized observations/evaluations**.

They do not independently decide:

```text
reroute
block
human review
change model
retrieve more
```

The ControlPlane Decision Engine combines their outputs with:

```text
policy
risk
confidence
impact
trajectory
budget
available capabilities
```

and chooses the next action.

This follows the Event Model rule that evaluators report observations while ControlPlane decides what happens next.

---

## 1.2 No giant evaluator model

Do not implement:

```text
one giant LLM
→ evaluates quality + reasoning + safety + privacy + bias + action risk + drift
```

Instead use modular evaluators with normalized contracts.

Some should be:

- deterministic/rule-based
- lightweight statistical
- LLM-based
- graph/state-based

Use the cheapest reliable mechanism for each task.

---

## 1.3 No unnecessary fine-tuning

The default implementation is:

```text
PRETRAINED / API MODEL
+
RULES / SIGNALS
+
NORMALIZED EVALUATION CONTRACT
```

Fine-tuning is allowed only after:

1. a baseline exists;
2. failure data is available;
3. the baseline is measured;
4. the new model has a clear expected improvement;
5. a train/validation/test split exists.

No component in this document is allowed to require fine-tuning for the initial prototype.

---

## 1.4 No hidden chain-of-thought storage

Do not store private model chain-of-thought.

Store only structured information such as:

```text
reason_code
evidence_ids
evaluation_scores
claims
observations
decision_rationale
```

The trajectory/ledger architecture explicitly excludes private model chain-of-thought as a stored artifact.

---

## 1.5 All component outputs are versioned

Every evaluator output should be associated with:

```text
evaluator_id
evaluator_version
policy_version
request_id
trace_id
trajectory_id
step_id
timestamp
```

This is mandatory for reproducibility.

---

# 2. Common Input Contract

All eight components should receive a normalized execution context.

Conceptually:

```json
{
  "request_id": "req_...",
  "trace_id": "trace_...",
  "trajectory_id": "traj_...",
  "step_id": "step_...",
  "query": "...",
  "response": "...",
  "context": {
    "retrieved_documents": [],
    "tool_results": [],
    "structured_data": [],
    "conversation_context": []
  },
  "execution_state": {
    "current_plan_version": 1,
    "route": "...",
    "models_used": [],
    "tools_used": [],
    "permissions": [],
    "data_accessed": []
  },
  "policy_context": {
    "application_policy": "...",
    "risk_tolerance": "...",
    "jurisdiction": "...",
    "data_policy": "..."
  }
}
```

Not every component uses every field.

The implementation must not duplicate unrelated state inside each evaluator.

---

# 3. Common Output Contract

Every evaluator should normalize to something conceptually similar to:

```json
{
  "evaluation_id": "eval_...",
  "evaluator_id": "grounding_v1",
  "evaluator_version": "1.0.0",
  "status": "PASS",
  "score": 0.0,
  "confidence": 0.0,
  "severity": "LOW",
  "issues": [],
  "evidence_refs": [],
  "recommended_signals": [],
  "metadata": {}
}
```

The exact schema can be refined in `docs/CONTRACTS/`, but the semantics must remain consistent.

### Important distinction

```text
score
=
evaluation measurement

confidence
=
confidence in the evaluation

severity
=
governance/operational importance

recommended_signals
=
possible control signals
```

Do not confuse evaluation confidence with model confidence.

---

# 4. Response Quality Evaluator

## 4.1 Purpose

Determine whether the final response is useful and acceptable with respect to:

```text
correctness
relevance
completeness
instruction following
clarity
```

This is an **output-quality evaluator**, not the system's final trust engine.

---

## 4.2 Inputs

Required:

```text
query
response
```

Preferred where available:

```text
reference_answer
retrieved_evidence
tool_results
conversation_context
policy_context
```

---

## 4.3 Output

Use structured dimensions:

```text
correctness
relevance
completeness
instruction_following
clarity
overall_quality
```

Recommended categorical output for the first prototype:

```text
ACCEPTABLE
ACCEPTABLE_WITH_LIMITATIONS
NEEDS_REPAIR
UNACCEPTABLE
INSUFFICIENT_INFORMATION
```

Numeric scores may be stored for experimentation, but the application should not treat arbitrary LLM scores as calibrated probabilities.

---

## 4.4 Initial implementation

### Baseline

Use an LLM judge with a fixed rubric.

The rubric should explicitly ask for:

```text
What was requested?
What did the response claim?
What is correct?
What is unsupported?
What important requirement was missed?
What evidence supports the judgment?
```

Do not ask the judge for hidden chain-of-thought.

Ask for structured reasons.

---

## 4.5 Research to study

### MT-Bench / Chatbot Arena

**Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena**

Use this to understand:

- usefulness of LLM judges
- pairwise evaluation
- judge bias
- position bias
- verbosity bias
- judge reliability

Reference:
https://arxiv.org/abs/2306.05685

### Prometheus

**Prometheus: Inducing Fine-grained Evaluation Capability in Language Models**

Use this for the idea of a dedicated evaluator model with rubric-based evaluation.

Reference:
https://arxiv.org/abs/2310.08491

---

## 4.6 Data requirement

### Initial

No special training dataset is required to start.

Use:

```text
100–300 human-validated evaluation cases
+
existing benchmark responses
```

The project data plan already targets 200–300 human-annotated cases.

### Fine-tuning

Optional later.

Only consider fine-tuning if:

```text
baseline judge disagreement with humans
>
acceptable threshold
```

and enough rubric-specific data exists.

Recommended later format:

```json
{
  "query": "...",
  "response": "...",
  "human_label": "NEEDS_REPAIR",
  "human_reason": "...",
  "evidence_refs": []
}
```

---

## 4.7 Do we need a local model?

**Not for V1.**

Start with:

```text
external LLM judge
```

A local evaluator can become V2.

---

## 4.8 Failure modes

- judge/model bias
- response verbosity bias
- missing reference truth
- judge hallucination
- evaluator disagreement
- overconfidence
- poor evaluation on specialized domains

---

# 5. Reasoning Evaluator

## 5.1 Purpose

Detect whether a response appears to rely on unreliable reasoning.

This is not:

```text
"read the model's private chain-of-thought"
```

Instead evaluate:

```text
logical validity
consistency
multi-step correctness
calculation correctness
evidence-to-conclusion consistency
```

---

## 5.2 Inputs

```text
query
response
structured evidence
tool outputs
reference answer where available
```

Optional:

```text
explicitly exposed reasoning steps
structured intermediate outputs
program traces
calculator/tool outputs
```

Do not require hidden reasoning traces.

---

## 5.3 Output

```text
reasoning_status:
VALID
MINOR_ISSUE
MAJOR_ISSUE
INVALID
NOT_APPLICABLE
```

Also:

```text
confidence
failure_type
evidence_refs
```

Potential failure types:

```text
LOGICAL_CONTRADICTION
INVALID_INFERENCE
UNSUPPORTED_CONCLUSION
ARITHMETIC_ERROR
MISSED_CONSTRAINT
CAUSALITY_ERROR
```

---

## 5.4 Initial implementation

Use a hybrid approach:

```text
deterministic checks
+
tool/result verification
+
LLM evaluator
```

Examples:

```text
Math:
calculator / deterministic checker

SQL:
verify result against DB

Code:
execute tests where safe

RAG:
claim/evidence verification

General reasoning:
rubric-based evaluator
```

This is stronger than using an LLM judge for everything.

---

## 5.5 Research

Study:

### SelfCheckGPT

Useful for black-box consistency-based hallucination/reliability detection.

Reference:
https://arxiv.org/abs/2303.08896

Also study the broader research area:

```text
process supervision
reasoning evaluation
self-consistency
verifiable reasoning
test-time compute
```

The project's adaptive test-time compute research reference is also useful for understanding why reasoning quality and computation allocation can be coupled.

---

## 5.6 Data requirement

Need:

```text
reasoning queries
+
correct/incorrect responses
+
human reasoning-quality labels
```

Recommended initial subset:

```text
50–100 reasoning-focused human-validated cases
```

Do not create a separate giant reasoning dataset yet.

---

## 5.7 Local model / fine-tuning

**No V1 local model required.**

Potential V2:

```text
small evaluator
```

trained on:

```text
query
response
reference/verification
reasoning_label
```

Do not fine-tune until baseline measurements exist.

---

# 6. Safety Evaluator

## 6.1 Purpose

Evaluate whether:

```text
content
request
response
tool proposal
action
trajectory
```

contains safety risk.

The safety evaluator must distinguish:

```text
content safety
```

from:

```text
action safety
```

Action safety belongs jointly to Safety + Action Risk + Policy.

---

## 6.2 Inputs

```text
query
response
tool proposal
trajectory
policy
application context
risk context
```

---

## 6.3 Outputs

```text
SAFE
POTENTIALLY_UNSAFE
UNSAFE
```

with:

```text
risk_category
severity
confidence
evidence_refs
```

Potential categories:

```text
VIOLENCE
SELF_HARM
ILLEGAL_ACTIVITY
SEXUAL_SAFETY
ABUSE
CYBER_ABUSE
PROMPT_INJECTION
MALICIOUS_TOOL_USE
DATA_EXFILTRATION
UNAUTHORIZED_ACTION
```

The exact taxonomy should be kept configurable.

---

## 6.4 Initial implementation

Use:

```text
policy rules
+
pretrained safety classifier where appropriate
+
LLM safety evaluator
+
tool/action policy checks
```

Do not make a single LLM classifier the only safety control.

---

## 6.5 Research

### SafeAgent

**SafeAgent: A Runtime Protection Architecture for Agentic Systems**

Useful for runtime action governance and stateful trajectory-level safety.

Reference:
https://arxiv.org/abs/2604.17562

### InjecAgent

**InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated LLM Agents**

Useful for the agent/tool attack surface and indirect prompt injection evaluation.

Reference:
https://arxiv.org/abs/2403.02691

---

## 6.6 Data requirement

Use:

```text
public safety benchmarks
+
synthetic adversarial cases
+
agent/tool safety trajectories
```

The project data plan specifically requires safe/unsafe/recoverable/unrecoverable trajectories.

---

## 6.7 Local model / fine-tuning

No V1 fine-tuning.

A small local safety classifier is optional later if:

```text
latency
cost
privacy
```

make an external safety model undesirable.

---

# 7. Privacy / PII Detector

## 7.1 Purpose

Detect sensitive data exposure.

This is deliberately designed as a **deterministic/lightweight component**, not an LLM-first problem.

---

## 7.2 Inputs

```text
query
response
retrieved documents
tool input
tool output
data-access event
```

---

## 7.3 Output

```json
{
  "status": "DETECTED",
  "entities": [
    {
      "type": "EMAIL",
      "start": 10,
      "end": 31,
      "sensitivity": "MEDIUM"
    }
  ]
}
```

Initial status:

```text
NONE
POTENTIAL_PII
PII_EXPOSURE
SENSITIVE_DATA_EXPOSURE
```

---

## 7.4 Initial implementation

Use:

```text
regex
+
deterministic validators
+
NER / PII recognizer
+
policy classification
```

Examples:

```text
email
phone
credit card
financial account
government identifier
employee ID
customer ID
private address
```

For a prototype, a tool such as Microsoft Presidio is a reasonable implementation direction.

Do not use an LLM for every PII check.

---

## 7.5 Data requirement

You need:

```text
synthetic PII examples
+
PII-free examples
+
edge cases
```

Create controlled synthetic data.

Do not put real user/company PII into the competition repository.

---

## 7.6 Fine-tuning

**No initial fine-tuning.**

Only consider adapting a local NER model if the synthetic enterprise schema contains unusual identifiers that standard recognizers systematically miss.

---

# 8. Bias Evaluator

## 8.1 Purpose

Detect meaningful differences in model behavior across controlled variants.

Do not attempt to solve "all bias."

Focus on:

```text
paired/counterfactual comparisons
```

---

## 8.2 Inputs

```text
query
response
counterfactual query
counterfactual response
evaluation rubric
```

Example:

```text
Query A:
Candidate is Alex.

Query B:
Candidate is Sam.

Everything else identical.
```

Compare:

```text
recommendation
tone
qualification
risk assessment
decision
```

---

## 8.3 Output

```text
NO_SIGNIFICANT_DIFFERENCE
POTENTIAL_BIAS
SIGNIFICANT_DIFFERENCE
```

plus:

```text
comparison_dimensions
evidence
severity
confidence
```

---

## 8.4 Initial implementation

Use:

```text
controlled counterfactual test generation
+
paired output comparison
+
LLM judge
+
deterministic statistical comparison where possible
```

This is much better than a generic:

```text
"Is this answer biased?"
```

prompt.

---

## 8.5 Data requirement

This requires **paired datasets**.

For example:

```text
query_A
query_B
protected_attribute_changed
response_A
response_B
metric_difference
human_label
```

Start with:

```text
50–100 paired cases
```

inside the broader evaluation corpus.

---

## 8.6 Fine-tuning

No.

A dedicated bias model is not justified for V1.

---

# 9. Behavioral Drift Monitor

## 9.1 Purpose

Detect whether actual execution is deviating from the expected trajectory.

This is a **runtime state monitor**, not a response evaluator.

---

## 9.2 Inputs

From the Trajectory Store / Execution Ledger:

```text
expected plan
actual nodes
tool calls
data sources
permissions
external destinations
action sensitivity
workflow length
monetary/action changes
```

The trajectory/ledger contract explicitly exists to expose these execution facts.

---

## 9.3 Output

```text
drift_score
drift_dimensions
severity
evidence_refs
```

Potential dimensions:

```text
TOOL_VELOCITY
DATA_SOURCE_DEVIATION
PERMISSION_DEVIATION
DESTINATION_DEVIATION
ACTION_SENSITIVITY
MONETARY_DEVIATION
WORKFLOW_LENGTH
PLAN_DEVIATION
```

---

## 9.4 Initial algorithm

**No ML model.**

Implement:

```text
expected trajectory
vs
observed trajectory
```

using configurable weighted signals.

Example conceptual formula:

```text
drift =
w1 * tool_deviation
+
w2 * data_source_deviation
+
w3 * permission_deviation
+
w4 * destination_deviation
+
w5 * action_deviation
```

Do not treat this as a calibrated probability.

Call it:

```text
behavioral drift score
```

not:

```text
P(unsafe)
```

---

## 9.5 Research

Use the research reference's behavioral-drift proposal as the architecture basis.

For more general anomaly-detection techniques, later investigate:

```text
sequence anomaly detection
graph anomaly detection
online change-point detection
```

Do not add a complex anomaly model to V1.

---

## 9.6 Data requirement

You need trajectory examples:

```text
normal
deviating
safe recovery
unsafe recovery
```

The data workstream already calls for 50–100 agent trajectories.

---

# 10. Action Risk Evaluator

## 10.1 Purpose

Evaluate proposed **external actions**, not just generated text.

Examples:

```text
send email
issue refund
modify CRM
delete record
publish content
execute API
transfer data
```

---

## 10.2 Inputs

```text
proposed_action
target
parameters
actor/agent
permissions
data involved
trajectory
policy
application
impact
reversibility
```

---

## 10.3 Output

```text
action_risk:
LOW
MEDIUM
HIGH
CRITICAL
```

and:

```text
ALLOW
MODIFY
HUMAN_REVIEW
BLOCK
```

The action result is still interpreted by ControlPlane policy.

---

## 10.4 Initial implementation

Use:

```text
action taxonomy
+
policy rules
+
permission checks
+
trajectory context
+
deterministic impact scoring
```

Example:

```text
read public data
→ low

update internal draft
→ medium

send external email
→ medium/high

issue large refund
→ high

delete production records
→ critical
```

Exact thresholds must be policy-configurable.

---

## 10.5 Data requirement

Create:

```text
50–100 synthetic action cases
```

including:

```text
safe
unsafe
ambiguous
high-impact
irreversible
requires human approval
```

---

## 10.6 Fine-tuning

No.

The first version should be policy/rule based.

Later, action-risk labels can support a learned risk estimator.

---

# 11. Permission / Data-Lineage Engine

## 11.1 Purpose

Track:

```text
who accessed what
under which permission
through which capability
where it went
```

This is a **graph problem**, not primarily an ML problem.

---

## 11.2 Input data model

Every relevant action should generate a lineage edge conceptually:

```text
subject
source
resource
permission
action
destination
timestamp
trajectory_id
```

Example:

```json
{
  "subject": "agent_A",
  "source": "crm",
  "resource": "customer_email",
  "permission": "customer_read",
  "action": "READ",
  "destination": "agent_B",
  "trajectory_id": "traj_123"
}
```

Another:

```json
{
  "subject": "agent_B",
  "source": "customer_record",
  "resource": "customer_email",
  "permission": "share_allowed",
  "action": "TRANSFER",
  "destination": "external_email",
  "trajectory_id": "traj_123"
}
```

---

## 11.3 Internal representation

Use a graph:

```text
Agent
  ↓
Permission
  ↓
Resource
  ↓
Agent
  ↓
Tool
  ↓
External Destination
```

Initially this can be represented using ordinary relational tables:

```text
subjects
permissions
resources
access_events
transfers
destinations
```

You do **not** need Neo4j initially.

A graph database becomes a future optimization only if query complexity justifies it.

---

## 11.4 Required detections

At minimum detect:

```text
UNAUTHORIZED_ACCESS
PERMISSION_ESCALATION
UNEXPECTED_DATA_TRANSFER
UNEXPECTED_DESTINATION
CROSS_AGENT_PERMISSION_LAUNDERING
SENSITIVE_DATA_EXPORT
```

---

## 11.5 Research basis

The trajectory architecture explicitly calls for permission lineage and data-flow visibility, especially because multi-agent sequences can compose into unsafe behavior.

The research reference also identifies permission laundering as a multi-agent risk.

---

## 11.6 Fine-tuning

**No.**

This should initially be deterministic graph/state analysis.

---

# 12. How These Eight Components Work Together

Do not run them as eight unrelated checks.

The execution should be:

```text
                       RESPONSE
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
       QUALITY         REASONING         SAFETY
          │               │                │
          └───────────────┼────────────────┘
                          │
                       PRIVACY
                          │
                        BIAS
                          │
                          ▼
                 TRAJECTORY STATE
                          │
                    ┌─────┴─────┐
                    ▼           ▼
                   DRIFT     PERMISSION
                    │         LINEAGE
                    └─────┬─────┘
                          ▼
                      ACTION RISK
                          │
                          ▼
                    DECISION ENGINE
```

The result is **one Control Decision**, not eight independent decisions.

---

# 13. Recommended P0 / P1 Implementation

## P0 — Required

Build first:

```text
1. Response Quality
2. Reasoning
3. Safety
4. Privacy / PII
5. Action Risk
6. Permission / Data Lineage
```

And the infrastructure needed for them:

```text
ExecutionState
Trajectory Store
Execution Ledger
Event Bus
Policy Engine
Decision Engine
```

The current architecture already identifies these runtime/governance contracts as first-class.

---

## P1 — Add after the control loop works

```text
7. Behavioral Drift
8. Bias
```

Reason:

They become much more useful when the trajectory/event/evaluation infrastructure already produces reliable data.

---

# 14. Local ML Model Requirement

The default answer for these eight components is:

```text
LOCAL ML MODELS REQUIRED NOW = 0
```

Initial system:

```text
Rules
+
Policy
+
Pretrained NER/PII tool
+
LLM evaluator
+
Structured state
+
Deterministic lineage
```

Then introduce **one small local model** only if the evaluation shows a concrete reason.

Best candidates:

```text
Candidate A:
query/risk classifier

Candidate B:
RAG/hallucination evaluator

Candidate C:
quality/rubric evaluator
```

Do not build one local model per evaluator.

---

# 15. Fine-Tuning Policy

Use this progression:

```text
V0
Rules / API / pretrained components

       ↓

V1
Benchmark + human validation

       ↓

V2
Small local model where baseline fails

       ↓

V3
Fine-tuning if enough labelled data exists

       ↓

V4
Continuous improvement / routing based on execution history
```

The project data plan explicitly requires human labels, intervention labels, counterfactuals, RAG cases, and agent trajectories.

Do not fine-tune before these datasets are stable.

---

# 16. Data Schema Required Across These Components

Create one normalized evaluation record.

Conceptually:

```json
{
  "case_id": "case_001",
  "request": {
    "query": "...",
    "intent": "...",
    "risk_profile": {}
  },

  "execution": {
    "plan_id": "...",
    "plan_version": 1,
    "route": "...",
    "trajectory_id": "...",
    "steps": []
  },

  "input": {
    "response": "...",
    "evidence_refs": [],
    "tool_calls": [],
    "data_access": [],
    "permissions": []
  },

  "evaluations": {
    "quality": {},
    "reasoning": {},
    "safety": {},
    "privacy": {},
    "bias": {},
    "drift": {},
    "action_risk": {},
    "lineage": {}
  },

  "control": {
    "decision": "...",
    "intervention": "...",
    "reason": "...",
    "expected_outcome": "..."
  },

  "outcome": {
    "final_status": "...",
    "trust": {},
    "cost": null,
    "latency_ms": null,
    "recovery_success": null
  }
}
```

Do not make every field mandatory for every case.

---

# 17. Human Annotation Data

For the human subset, use structured annotations:

```text
quality
grounding
reasoning
safety
privacy
action_risk
bias
preferred_intervention
reason
```

and:

```text
label_source:
HUMAN
EXPERT
LLM_JUDGE
AUTOMATIC
SYNTHETIC
DERIVED
```

Never treat an LLM-generated label as automatically equivalent to human ground truth.

At least 20% of human cases should be double-annotated under the existing data workstream.

---

# 18. Evaluation Metrics for the Eight Components

## Response Quality

```text
human agreement
judge agreement
pairwise preference accuracy
```

## Reasoning

```text
reasoning classification accuracy
task correctness
verification success
```

## Safety

```text
precision
recall
false positive rate
false negative rate
```

## Privacy/PII

```text
entity precision
entity recall
leak detection rate
```

## Bias

```text
paired outcome difference
false disparity rate
human agreement
```

## Behavioral Drift

```text
drift detection precision/recall
false intervention rate
missed drift rate
```

## Action Risk

```text
risk classification accuracy
unsafe-action catch rate
false block rate
```

## Permission/Data Lineage

```text
unauthorized-access detection
unexpected-transfer detection
lineage completeness
```

---

# 19. Most Important System-Level Metric

Do not optimize these components independently.

Eventually measure:

```text
                    BASELINE
                       vs
                  CONTROLPLANE
```

for:

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

> **Did ControlPlane improve the outcome sufficiently to justify the additional control overhead?**

The product architecture explicitly prioritizes quality, trust, safety, adaptivity, efficiency, latency, recoverability, auditability, and scalability together.

---

# 20. Do Not Build These as Separate Microservices Yet

For the competition prototype:

```text
DO NOT create:
quality_service
reasoning_service
safety_service
privacy_service
bias_service
drift_service
risk_service
lineage_service
```

unless load testing or clear ownership boundaries justify it.

Prefer:

```text
ControlPlane Evaluation Package
├── quality
├── reasoning
├── safety
├── privacy
├── bias
├── drift
├── action_risk
└── lineage
```

with stable interfaces.

Scale them later if necessary.

This is consistent with the scale architecture's explicit warning against unnecessary distributed-system complexity for the 10,000/week competition workload.

---

# 21. Coding-Agent Implementation Rules

Before implementing any one of these components, the agent MUST:

1. Read this document.
2. Read `PRODUCT_THESIS.md`.
3. Read `docs/ARCHITECTURE.md`.
4. Read `RUNTIME_FLOW.md`.
5. Read `EVENT_MODEL.md`.
6. Read `TRAJECTORY_AND_LEDGER.md`.
7. Read `FAILURE_AND_RECOVERY.md`.
8. Read the relevant research note.
9. Read the relevant algorithm specification.
10. Inspect existing contracts/tests.

The agent must then produce:

```text
implementation plan
+
interface
+
data schema
+
tests
+
documentation
```

before expanding implementation scope.

---

# 22. Anti-Hallucination Rules for Coding Agents

The coding agent MUST NOT:

- invent unavailable datasets
- invent benchmark results
- claim an evaluator is calibrated when it is not
- introduce a new model without documenting why
- fine-tune without a dataset and evaluation plan
- create a database because "it might scale"
- create a graph database merely because lineage is graph-shaped
- store model chain-of-thought
- create a separate service without an architectural reason
- let an evaluator directly trigger another route
- make MCP responsible for routing
- replace policy with an LLM prompt
- use a score as a probability without calibration
- silently introduce new thresholds
- silently change the execution contract
- claim rollback without a real rollback mechanism

If a requirement is not defined:

```text
STATUS = OPEN QUESTION
```

Do not invent an answer.

---

# 23. Research/Implementation Status Table

| Component | V1 mechanism | Local model now? | Fine-tuning now? | Data required now? |
|---|---|---:|---:|---|
| Response Quality | LLM judge + rubric | No | No | Human validation |
| Reasoning | LLM judge + deterministic verification | No | No | Reasoning cases |
| Safety | Rules + safety classifier/judge + policy | No | No | Safety/agent cases |
| Privacy / PII | Regex + NER/PII recognizer | Optional pretrained | No | Synthetic PII |
| Bias | Paired counterfactual + judge | No | No | Paired cases |
| Behavioral Drift | Weighted trajectory signals | No | No | Agent trajectories |
| Action Risk | Policy + deterministic impact scoring | No | No | Action cases |
| Permission/Data Lineage | Graph/relational lineage | No | No | Synthetic access traces |

---

# 24. Future Algorithm Candidates

These are **research candidates**, not implementation commitments.

## Quality

```text
LLM-as-a-Judge
Prometheus-style evaluator
pairwise preference evaluation
```

## Reasoning

```text
self-consistency
process evaluation
verifiable reasoning
```

## Safety

```text
runtime safety classifier
agent trajectory safety
tool-use safety
prompt-injection detection
```

## Privacy

```text
NER
PII recognition
policy-based classification
```

## Bias

```text
counterfactual testing
paired evaluation
statistical parity-style analysis where applicable
```

## Drift

```text
weighted rules
change-point detection
sequence anomaly detection
graph anomaly detection
```

## Action Risk

```text
risk rules
policy engine
learned risk estimator later
```

## Permission/Data Lineage

```text
relational lineage
graph traversal
reachability analysis
policy violation detection
```

---

# 25. Required Deliverables Before Coding These Components

For each of the eight components, create:

```text
docs/ALGORITHMS/<component>.md
```

with:

```text
Problem
Inputs
Outputs
Baseline
Research candidates
Data requirements
Training requirements
Evaluation metrics
Failure modes
Latency expectation
Cost expectation
Prototype decision
Future alternatives
Open questions
```

Do not begin implementation until the component's baseline is clearly specified.

---

# 26. Final Decision

For the competition prototype, the recommended architecture is:

```text
                 EVALUATION / GOVERNANCE

Response Quality
Reasoning
Safety
Privacy / PII
Bias
Behavioral Drift
Action Risk
Permission / Data Lineage
              │
              ▼
      Normalized Signals
              │
              ▼
       ControlPlane Decision
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
   Continue  Verify  Intervene
                       │
                 ┌─────┼─────┐
                 ▼     ▼     ▼
              Reroute Replan Human
                       │
                       ▼
                    Verify
                       │
                       ▼
                  Final Result
```

The eight components are therefore **sensors/control signals inside one decision architecture**, not eight independent AIs.

---

# 27. Final Implementation Rule

The coding agent must always distinguish:

```text
ARCHITECTURAL REQUIREMENT
        vs
ALGORITHM CHOICE
        vs
IMPLEMENTATION CHOICE
        vs
RESEARCH HYPOTHESIS
```

Example:

```text
Requirement:
"Detect PII."

Algorithm:
"NER + deterministic recognizer."

Implementation:
"Presidio + regex."

Research hypothesis:
"A fine-tuned NER model may improve enterprise-specific identifier recall."
```

These are not the same thing.

The architecture is already fixed enough to support experimentation. The algorithm can evolve beneath the contract without changing the product.

**Do not redesign the architecture while implementing an algorithm unless a measured result proves the existing contract is insufficient.**
