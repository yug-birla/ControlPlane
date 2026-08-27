# ControlPlane.ai — Data & Evaluation Workstream
## Detailed Instructions for Data Team — 2-Person Parallel Work

**Objective:** Build the evaluation, annotation, benchmark, and intervention data needed to prove that ControlPlane can understand a request, select a route, detect failures, intervene, replan, and improve the final outcome while tracking quality, risk, cost, and latency.

---

## 1. Do Not Treat This as a Normal QA Dataset

A simple dataset:

```text
query → answer
```

is insufficient.

ControlPlane needs evidence for:

```text
query
→ query profile
→ required capabilities
→ initial route
→ execution
→ observations/events
→ failure or uncertainty
→ intervention
→ replanned route
→ final outcome
→ quality + trust + cost + latency
```

The central evaluation loop is:

```text
UNDERSTAND → PLAN → EXECUTE → OBSERVE → EVALUATE
                    ↓
              FAILURE / SIGNAL
                    ↓
               INTERVENE
                    ↓
                REPLAN
                    ↓
                VERIFY
                    ↓
               FINAL ANSWER
```

---

# 2. Team Split

## Person A — External Dataset & Benchmark Research Lead

Find, inspect, score, and integrate existing public datasets.

Focus on:

- factuality / hallucination
- RAG
- retrieval quality
- safety
- privacy / PII
- bias / fairness
- LLM-as-a-judge / preference
- reasoning
- model routing
- model selection
- cost/latency-aware inference
- agent safety
- agent trajectories
- tool use

**Do not merely collect links.** Inspect the actual dataset card, schema, samples, license, annotation method, and limitations.

---

## Person B — ControlPlane Custom Dataset & Annotation Lead

Build what existing benchmarks do not adequately provide.

Focus on:

- query profiling
- risk profiling
- capability routing
- route selection
- failure cases
- intervention decisions
- replanning
- self-healing
- model switching
- RAG insufficiency
- model disagreement
- cost/latency trade-offs
- agentic intervention
- human annotation
- counterfactual route comparisons

**Person B owns the annotation schema and guidelines.**

---

# 3. Anti-Duplication Rule

```text
Person A → What already exists
Person B → What is missing
```

If Person A discovers an external dataset covering a Person B gap:

1. Add it to the registry.
2. Mark the gap as potentially covered.
3. Tell Person B.
4. Do not silently redesign the internal schema.

---

# 4. Initial Dataset Targets

These are planning targets, not quotas to fill with low-quality data.

## Query profiles

**200–300 unique queries**

Initial coverage:

| Query type | Target |
|---|---:|
| Public factual | 25 |
| Private/enterprise factual | 25 |
| RAG/document QA | 30 |
| Insufficient RAG | 20 |
| SQL/structured data | 20 |
| Analytical | 20 |
| Complex reasoning | 25 |
| Coding | 15 |
| Recommendation/decision support | 15 |
| Personal/memory | 10 |
| Chat history | 10 |
| Agentic | 15 |
| High-risk agentic | 10 |

Categories can overlap.

---

## Model responses

**500–1,000 responses**

Use approximately 2–4 model/capability variants for selected queries rather than every model for every query.

---

## Human annotation

**200–300 deeply annotated cases**

---

## RAG

**100–200 cases**

Include:

- answerable
- partially answerable
- insufficient
- irrelevant retrieval
- conflicting evidence
- stale evidence
- missing documents

---

## Intervention

**100–200 cases**

Candidate interventions:

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
OTHER
```

This is the same 16-label intervention taxonomy used throughout — see `ANNOTATION_GUIDELINES.md` and §20 below.

---

## Agent trajectories

**50–100 trajectories**

Include safe, unsafe, recoverable, unrecoverable, wrong-tool, unnecessary-tool, and human-approval-required cases.

---

# 5. Dataset Layers

Use these conceptual layers:

```text
Layer 1 — Query
Layer 2 — Response
Layer 3 — Retrieval / Evidence
Layer 4 — Execution / Route
Layer 5 — Failure
Layer 6 — Intervention
Layer 7 — Agent Trajectory
Layer 8 — Human Judgment
Layer 9 — Outcome
```

Not every sample needs every layer.

---

# 6. Person A — Where to Search

## Hugging Face

Search:

```text
site:huggingface.co/datasets LLM evaluation
site:huggingface.co/datasets hallucination benchmark
site:huggingface.co/datasets RAG evaluation
site:huggingface.co/datasets retrieval evaluation
site:huggingface.co/datasets agent safety
site:huggingface.co/datasets tool use agent
site:huggingface.co/datasets LLM preference
site:huggingface.co/datasets model routing
```

Inspect:

- dataset card
- license
- sample count
- fields
- source
- annotation method
- human vs synthetic labels
- splits
- limitations

## Papers With Code

Search:

```text
LLM evaluation
RAG evaluation
hallucination
agent safety
LLM routing
LLM judge
model selection
```

Follow paper → dataset → GitHub → download links.

## GitHub

Search:

```text
LLM evaluation dataset
RAG benchmark dataset
agent safety benchmark
LLM routing benchmark
LLM judge dataset
LLM hallucination dataset
tool use benchmark
```

Always inspect the LICENSE and actual data files.

## Research venues

Search relevant papers in:

- arXiv
- ACL Anthology
- NeurIPS
- ICML
- ICLR
- EMNLP
- NAACL
- AAAI
- KDD
- WWW

Useful searches:

```text
"LLM routing" dataset benchmark
"model routing" language models
"RAG evaluation" benchmark dataset
"agent safety" benchmark trajectory
"LLM judge" human preference dataset
"hallucination evaluation" dataset
"tool use" agent benchmark
"adaptive inference" language model routing
"cascade routing" LLM
```

---

# 7. Research Areas Person A Must Cover

## RAG

Search:

```text
RAGAS
ARES RAG evaluation
RAG benchmark
retrieval relevance benchmark
groundedness dataset
faithfulness dataset
```

Look for:

```text
context relevance
context sufficiency
answer faithfulness
answer relevance
retrieval quality
```

## LLM-as-a-Judge

Search:

```text
LLM judge benchmark
LLM evaluation judge reliability
pairwise LLM evaluation
human preference LLM dataset
```

Record known issues such as:

- position bias
- verbosity bias
- judge/model bias
- disagreement with humans

## Model Routing

Search:

```text
LLM routing
model routing
LLM router
cost-aware LLM routing
quality-aware model selection
adaptive model routing
cascade routing
```

Prioritize data containing:

```text
query
model outputs
quality
cost
latency
```

## Hallucination / Factuality

Search:

```text
LLM hallucination benchmark
factuality benchmark
faithfulness dataset
claim verification dataset
```

Prefer datasets with:

```text
claim + evidence + judgment
```

## Agent Safety

Search:

```text
agent safety benchmark
LLM agent trajectory benchmark
tool use safety
agent action safety
unsafe tool call benchmark
```

Look for:

```text
task
trajectory
tool call
tool result
risk
unsafe action
intervention
```

---

# 8. External Dataset Scorecard

Create:

```text
data/reports/dataset_scorecard.csv
```

Required columns:

```text
dataset_name
paper
source_url
github_url
license
domain
task
num_samples
human_annotated
synthetic
query_available
response_available
context_available
retrieval_available
trajectory_available
intervention_available
cost_available
latency_available
risk_labels
quality_labels
factuality_labels
safety_labels
privacy_labels
bias_labels
pairwise_labels
train_split
validation_split
test_split
data_format
download_status
license_status
relevance_score
priority
integration_effort
notes
```

---

# 9. Relevance Scoring

Use 0–5:

```text
5 = directly useful to ControlPlane
4 = highly useful, minor transformation
3 = useful for one ControlPlane component
2 = indirect support
1 = low relevance
0 = reject
```

Priority:

```text
P0 = required
P1 = strong value
P2 = optional
P3 = reference only
REJECT
```

Do not download everything.

Target:

```text
30–50 candidates
→ 15–20 serious candidates
→ 8–12 selected
→ 5–8 actually integrated
```

---

# 10. Person B — Custom Dataset

Before generating large amounts of data, create:

```text
docs/DATA/SCHEMA.md
docs/DATA/ANNOTATION_GUIDELINES.md
docs/DATA/DATA_GENERATION.md
```

Then create **30 representative examples** and review the schema.

Only after the schema is stable should large-scale generation begin.

---

# 11. Query Dataset

Create **200–300 queries**.

Each record should contain approximately:

```text
query_id
query
intent
domain
knowledge_type
required_data_sources
required_capabilities
complexity
risk
actionability
sensitivity
ambiguity
expected_route
```

Initial taxonomy:

```text
PUBLIC_FACTUAL
PRIVATE_FACTUAL
RAG
INSUFFICIENT_RAG
SQL
ANALYTICAL
REASONING
CODING
RECOMMENDATION
DECISION_SUPPORT
MEMORY
CHAT_HISTORY
AGENTIC
HIGH_RISK_AGENTIC
SENSITIVE
AMBIGUOUS
MULTI_SOURCE
MULTI_STEP
```

Queries may have multiple labels.

---

# 12. Build Queries That Force Different Routes

Do not make 300 generic factual questions.

Examples:

### Public factual

```text
What is the capital of France?
```

Expected capability:

```text
fast/general model
```

### Enterprise data

```text
What was our Q4 revenue?
```

Expected:

```text
SQL / enterprise DB
```

### Policy

```text
According to this policy document, can X be approved?
```

Expected:

```text
RAG + verification
```

### Decision support

```text
Should we acquire company X?
```

Expected:

```text
external/private data + reasoning + verification
```

### Agentic

```text
Send the customer a refund of ₹50,000.
```

Expected:

```text
agentic + financial risk + authorization/human approval
```

### Memory

```text
Based on our previous conversations, what did I decide?
```

Expected:

```text
chat history / memory
```

---

# 13. Deliberately Create Failure Cases

This is one of the highest-priority tasks.

Create cases where:

```text
RAG → document missing
SQL → required field unavailable
Retriever → irrelevant documents
Model → reasoning failure
Verifier → model disagreement
Agent → unsafe tool call
Data → stale information
Memory → wrong context
Web → conflicting sources
```

We need both:

```text
normal cases
+
failure-triggering cases
```

---

# 14. Intervention Dataset

For each failure:

```text
case_id
initial_route
failure
severity
evidence
possible_interventions
preferred_intervention
reason
expected_effect
cost_effect
latency_effect
risk_effect
```

Example:

```text
failure:
INSUFFICIENT_RAG

possible:
RETRIEVE_MORE
SQL
ASK_USER
ABSTAIN

preferred:
RETRIEVE_MORE

reason:
The required information may exist in the document collection.
```

---

# 15. Counterfactual Dataset

Create **50–100 counterfactual cases**.

Schema:

```text
query
route_A
result_A
route_B
result_B
which_is_better
why
cost_A
cost_B
latency_A
latency_B
```

Purpose:

> Determine whether ControlPlane should switch routes.

Include examples where:

```text
cheap + fast + worse quality
vs
expensive + slow + better quality
```

The preferred route should depend on the query's quality, cost, and latency requirements.

---

# 16. RAG Dataset

Create **100–200 cases**.

Suggested distribution:

```text
50% answerable
25% partially answerable
25% insufficient
```

Include:

```text
irrelevant retrieval
partially relevant retrieval
conflicting documents
outdated documents
missing documents
```

Record:

```text
query
documents
retrieved_documents
document_relevance
evidence_sufficiency
ground_truth
expected_answer
```

The key question is:

> **Is the retrieved evidence sufficient to answer the query?**

---

# 17. Synthetic Enterprise Environment

Do not use real confidential data.

Create:

```text
data/synthetic_enterprise/
├── database/
├── documents/
└── chat/
```

Target:

```text
5–10 SQL tables
20–50 policy/product/financial documents
50–100 synthetic chat-history records
```

Possible tables:

```text
employees
customers
products
orders
transactions
revenue
support_tickets
departments
```

Documents:

```text
HR policies
financial policies
security policies
product documentation
customer policies
approval policies
```

This gives ControlPlane a realistic multi-source environment:

```text
Query
 ↓
SQL / RAG / Chat DB / Memory
```

---

# 18. Agent Trajectory Dataset

Create **50–100 trajectories**.

Record:

```text
trajectory_id
user_request
plan
step_1
tool_call
tool_result
step_2
tool_call
tool_result
final_action
final_answer
risk
intervention_point
expected_control_action
```

Include:

```text
SAFE
UNSAFE
RECOVERABLE
UNRECOVERABLE
WRONG_TOOL
UNNECESSARY_TOOL
HUMAN_APPROVAL_REQUIRED
```

The key annotation is:

> At which step should ControlPlane have intervened?

---

# 19. Human Annotation Schema

Start with **200–300 cases**.

### Correctness

```text
CORRECT
MOSTLY_CORRECT
PARTIALLY_CORRECT
INCORRECT
NOT_ENOUGH_INFORMATION
```

### Grounding

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTED
NOT_APPLICABLE
```

### Safety

```text
SAFE
POTENTIALLY_UNSAFE
UNSAFE
```

### Privacy

```text
NONE
POTENTIAL_PII
PII_EXPOSURE
SENSITIVE_DATA_EXPOSURE
```

### Reasoning

```text
VALID
MINOR_ERROR
MAJOR_ERROR
INVALID
NOT_APPLICABLE
```

### Action risk

```text
NO_ACTION
LOW_RISK
MEDIUM_RISK
HIGH_RISK
CRITICAL
```

---

# 20. Most Important Human Label

For relevant cases, ask:

> **What should ControlPlane do next?**

Allowed labels:

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
OTHER
```

Also require a **1–3 sentence WHY explanation**.

Example:

```text
The retrieved documents do not contain the requested Q4 revenue.
The system should query the authorized financial database rather than generate an unsupported answer.
```

---

# 21. Annotation Provenance

Every label must say where it came from:

```text
HUMAN
EXPERT
LLM_JUDGE
AUTOMATIC
SYNTHETIC
DERIVED
```

Never silently treat LLM-generated labels as ground truth.

---

# 22. Double Annotation

At least **20%** of human-labeled cases should be independently labeled by two annotators.

For 250 cases:

```text
250 × 20% = 50
```

Record:

```text
agreement_rate
disagreements
adjudicated_label
```

If disagreement is high:

1. identify ambiguous guidelines
2. revise annotation instructions
3. re-annotate affected cases
4. only then scale up

---

# 23. Data Quality

Reject or quarantine:

- missing required fields
- broken encoding
- duplicate IDs
- contradictory labels
- unclear annotation
- missing provenance
- unknown license
- unauthorized personal data
- benchmark leakage
- test examples accidentally used for tuning

Deduplicate at minimum using:

```text
exact hash
normalized-text hash
```

For large collections, investigate semantic duplicates.

---

# 24. Data Provenance

For external data record:

```text
dataset_name
source_url
paper_url
github_url
license
download_date
version
original_author
citation
modifications
```

For generated data record:

```text
generator
generation_date
prompt_version
model
temperature
seed if applicable
source_documents
generation_method
validation_method
```

---

# 25. Dataset Splits

Use:

```text
TRAIN
VALIDATION
TEST
CHALLENGE
```

Initial planning split:

```text
60% train
15% validation
15% test
10% challenge
```

The challenge set must be protected from routine tuning.

Prefer scenario-level separation over purely random splitting where leakage is possible.

---

# 26. Challenge Set

Make the challenge set intentionally difficult:

```text
ambiguous query
conflicting evidence
insufficient retrieval
model disagreement
high-risk action
latency pressure
cost pressure
missing data
wrong tool
unsafe tool
```

Do not repeatedly optimize directly against the challenge set.

---

# 27. Balance

Avoid a dataset dominated by easy factual questions.

Initial target:

```text
Easy / low risk        20%
Normal                 30%
Complex                20%
Failure-triggering     20%
High-risk/adversarial  10%
```

These are starting targets and can be adjusted after exploratory analysis.

---

# 28. Repository Structure

Create:

```text
data/
├── README.md
├── raw/
│   ├── external/
│   └── generated/
├── processed/
├── annotations/
├── evaluation/
│   ├── train/
│   ├── validation/
│   ├── test/
│   └── challenge/
├── synthetic_enterprise/
│   ├── database/
│   ├── documents/
│   └── chat/
├── schemas/
├── scripts/
└── reports/
```

Every major folder needs a README.

---

# 29. Required Documentation

Create:

```text
docs/DATA/
├── DATA_STRATEGY.md
├── DATASET_REGISTRY.md
├── ANNOTATION_GUIDELINES.md
├── DATA_GENERATION.md
├── SCHEMA.md
├── EVALUATION_PROTOCOL.md
├── DATA_QUALITY.md
├── DATASET_GAPS.md
└── DATA_CHANGELOG.md
```

---

# 30. Person A — Exact Workflow

## Day 1

1. Read product thesis and architecture.
2. Create dataset registry.
3. Find 30–50 candidate datasets.
4. Record all candidates.
5. Do not download everything.

## Day 2

1. Shortlist 15–20.
2. Check licenses.
3. Inspect schemas.
4. Inspect actual samples.
5. Evaluate annotation quality.
6. Score relevance.

## Day 3

1. Select 8–12.
2. Download/sample selected datasets.
3. Inspect transformation requirements.
4. Document gaps.

## Day 4+

1. Integrate highest-priority datasets.
2. Normalize schema.
3. Deduplicate.
4. Build evaluation splits.
5. Produce quality report.

---

# 31. Person B — Exact Workflow

## Day 1

1. Read this document.
2. Define schema.
3. Define taxonomy.
4. Create 30 representative queries.
5. Review schema.
6. Freeze v0.1.

## Day 2

1. Create 200–300 query profiles.
2. Ensure route diversity.
3. Create synthetic enterprise environment.
4. Create initial failure cases.

## Day 3

1. Generate model outputs.
2. Create RAG cases.
3. Create intervention cases.
4. Create counterfactual cases.

## Day 4

1. Prepare 200–300 annotation cases.
2. Apply annotation guidelines.
3. Double-annotate 20%.
4. Measure agreement.
5. Fix ambiguous guidelines.

## Day 5+

1. Generate 50–100 agent trajectories.
2. Add challenge cases.
3. Build final evaluation splits.
4. Produce quality report.

---

# 32. Joint Review

After initial research, create:

```text
Existing Data
vs
Required ControlPlane Data
```

Use a matrix:

| Requirement | Existing Dataset | Quality | Missing? | Internal Data Needed? |
|---|---|---:|---|---|
| Query profiling | | | | |
| Factuality | | | | |
| RAG | | | | |
| Intervention | | | | |
| Routing | | | | |
| Agent safety | | | | |
| Cost | | | | |
| Latency | | | | |
| Replanning | | | | |
| Trust | | | | |

Do not invent the scores. Fill them only after inspecting the datasets.

---

# 33. Expected Major Gap

Existing benchmarks will probably be stronger at:

```text
"Was the answer good?"
```

than:

```text
"What should the control layer do next?"
```

That is not a problem.

The custom dataset should specifically cover:

```text
OBSERVATION
→ CONTROL DECISION
→ INTERVENTION
→ OUTCOME
```

This is central to ControlPlane's differentiation.

---

# 34. Metrics the Data Must Enable

## Query intelligence

```text
intent accuracy
data-source classification
risk classification
capability classification
```

## Routing

```text
route accuracy
wrong-route rate
unnecessary escalation
```

## Failure detection

```text
failure precision
failure recall
false intervention rate
missed failure rate
```

## Intervention

```text
intervention accuracy
recovery success
recovery failure
```

## Final outcome

```text
correctness
grounding
factuality
reasoning
safety
```

## Efficiency

```text
latency
cost
model calls
tool calls
tokens
```

Do not define a final composite metric until the architecture/evaluation leads agree on it.

---

# 35. Final Experiment the Dataset Must Enable

Run the same workload through:

```text
                 SAME QUERY SET
                       │
            ┌──────────┴──────────┐
            ↓                     ↓
       BASELINE LLM          CONTROLPLANE
            │                     │
            ↓                     ↓
          Answer             Dynamic Route
                                  ↓
                             Observe
                                  ↓
                            Verify/Replan
                                  ↓
                                Answer
```

Compare:

| Metric | Baseline | ControlPlane |
|---|---:|---:|
| Quality | | |
| Factuality | | |
| Grounding | | |
| Safety | | |
| Failure detection | | |
| Recovery rate | | |
| Cost | | |
| Latency | | |
| Model calls | | |
| Tool calls | | |
| Abstention quality | | |

Never fill values until experiments are actually run.

---

# 36. Final Deliverables

## Person A

```text
1. DATASET_REGISTRY.md
2. dataset_scorecard.csv
3. 30–50 candidates
4. 8–12 selected datasets
5. 5–8 integrated datasets
6. license/provenance report
7. dataset gap analysis
8. normalized samples
9. external-data README files
10. DATA_CHANGELOG.md
```

## Person B

```text
1. ANNOTATION_GUIDELINES.md
2. SCHEMA.md
3. 200–300 query profiles
4. 100–200 RAG cases
5. 100–200 intervention cases
6. 50–100 counterfactual cases
7. 50–100 agent trajectories
8. 200–300 human-annotated cases
9. synthetic enterprise corpus
10. annotation agreement report
11. challenge set
12. data quality report
```

---

# 37. The Core Principle

Do **not** optimize for dataset size.

Optimize for:

> **ControlPlane decision coverage.**

A 1,000-example dataset covering:

```text
query understanding
routing
failure detection
intervention
replanning
trust
cost
latency
agent safety
```

is more useful to this project than a 100,000-example dataset containing only:

```text
question → answer
```

The data work is successful only when it allows us to demonstrate:

```text
ControlPlane detected a problem
        ↓
understood why it mattered
        ↓
selected an intervention
        ↓
replanned execution
        ↓
improved the result
        ↓
reduced risk
        ↓
while respecting cost/latency constraints
```
