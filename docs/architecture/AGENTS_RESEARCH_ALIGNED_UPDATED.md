# AGENTS.md — ControlPlane.ai Agent Operating Instructions

## 0. READ THIS FIRST

You are an implementation agent working on **ControlPlane.ai**.

This repository is not a generic LLM application. It is an experimental, research-oriented **runtime AI Control Plane** whose architecture, contracts, observability, documentation, and experimental traceability are as important as the code.

Before modifying code:

1. Read `PRODUCT_THESIS.md`.
2. Read `docs/ARCHITECTURE.md`.
3. Read `docs/PROJECT_STATE/CURRENT_STATE.md`.
4. Read `docs/PROJECT_STATE/PROGRESS.md`.
5. Read `docs/PROJECT_STATE/FUTURE_WORK.md`.
6. Read the relevant component/folder README.
7. Read the relevant contract and algorithm document before changing an intelligent component.
8. Inspect existing tests before implementing anything.

**Do not start coding immediately after receiving a task. First determine where the task belongs in the architecture.**

---

# 1. Product Thesis — Do Not Drift

ControlPlane.ai is:

> **An adaptive, model-agnostic AI control plane that transforms a user request into a dynamic execution plan, coordinates models, data sources, retrieval systems, tools and verifiers, continuously monitors execution, detects quality/cost/responsibility failures, dynamically replans and self-heals the workflow, controls unsafe actions, and returns the best available answer with transparent evidence, trust, limitations, and audit history.**

The central loop is:

```text
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
REPLAN / SELF-HEAL
    ↓
VERIFY
    ↓
RESPOND
    ↓
LEARN
```

Do not reduce the product to:

- a chatbot
- a model comparison tool
- a dashboard
- a static model router
- an LLM-as-judge wrapper
- a safety filter
- a RAG evaluator
- an MCP demo

These are capabilities inside the product, not the product itself.

---

# 2. Core Architectural Rule

## CONTROLPLANE IS THE BRAIN

The architecture has four distinct responsibilities:

```text
ControlPlane Core
    = intelligence + state + policy + decision + replanning

Execution Graph
    = what should happen

Event Bus
    = what happened / what changed

MCP Capability Fabric
    = how capabilities are discovered and invoked
```

### Mandatory rule

> **DO NOT LET MCP BECOME THE BRAIN.**

MCP is a capability/interoperability fabric.

ControlPlane owns:

- query understanding
- execution planning
- route selection
- risk decisions
- policy
- trust
- interventions
- replanning
- human escalation
- authorization decisions
- learning

MCP provides:

- standardized capability discovery
- standardized invocation
- communication with tools/services
- access to models/data/retrieval/enterprise systems

Never implement core routing or policy logic inside MCP adapters.

---

# 3. Dynamic Execution Is the Core Innovation

The initial route is never assumed to be permanently correct.

Correct:

```text
Query
 ↓
Initial Profile
 ↓
Initial Plan
 ↓
Execute
 ↓
New Evidence
 ↓
Event
 ↓
ControlPlane
 ↓
Replan
 ↓
Execute Again
 ↓
Verify
```

Incorrect:

```text
Query
 ↓
Classifier
 ↓
One fixed route
 ↓
Answer
```

Every non-trivial capability should be able to communicate discoveries through events.

Examples:

```text
RETRIEVAL_INSUFFICIENT
DATA_REQUIRED
DATA_UNAVAILABLE
MODEL_DISAGREEMENT
HIGH_REASONING_UNCERTAINTY
EVIDENCE_CONFLICT
HIGH_ACTION_RISK
PII_DETECTED
VERIFICATION_FAILED
```

The capability reports the event.

The ControlPlane decides what happens next.

---

# 4. No Direct Route-to-Route Control

Never create hard-coded chains such as:

```python
rag_route -> sql_route()
```

Instead:

```text
RAG Route
   ↓
Event: DATA_REQUIRED
   ↓
Event Bus
   ↓
ControlPlane Decision Engine
   ↓
Replanner
   ↓
SQL Route
```

This maintains loose coupling and keeps ControlPlane authoritative.

---

# 5. Query Intelligence Must Be Multi-Dimensional

Never reduce a query to one category such as `"finance"`.

A Query Fingerprint should capture at least:

```text
intent
domain
data_requirements
complexity
sensitivity
impact
actionability
risk_vector
```

Risk dimensions may include:

```text
factuality
hallucination
reasoning
privacy
PII
security
bias
compliance
financial
action
reputational
```

A query may have multiple simultaneous labels.

Example:

```text
Analytical
+
Enterprise Finance
+
Confidential
+
High Impact
+
High Complexity
+
Decision Support
+
SQL + Documents
```

Query classification is **provisional** and can be updated by new evidence.

---

# 6. Execution Plans Must Be First-Class Objects

Never bury the route inside application code.

Represent it explicitly:

```text
plan_id
plan_version
steps
dependencies
parallel_groups
required_capabilities
verification_level
human_approval
cost_budget
latency_budget
policy
fallbacks
```

Plans must be versioned.

Every change creates a new plan version.

Example:

```text
Plan v1:
Fast Model

Plan v2:
Fast Model → Reasoning Model → Verifier

Reason:
HIGH_REASONING_UNCERTAINTY
```

---

# 7. Execution Graph Requirements

The execution graph must support:

- node creation
- node execution
- node completion
- failure
- retry
- skip
- replacement
- insertion
- deletion
- rerouting
- parallel branches
- synchronization
- human pause
- termination

Do not hard-code graphs as nested function calls if the behavior is expected to change at runtime.

---

# 8. Shared Execution State Is Mandatory

Every request must have a traceable execution state containing at least:

```text
request_id
query
query_profile
current_plan
plan_version
current_step
completed_steps
pending_steps
evidence
risk_state
confidence
model_calls
tool_calls
retrieval_calls
cost
latency
events
interventions
final_answer
trust_report
```

Every capability that changes meaningful execution state must update the state through the agreed interface.

---

# 9. Event Bus Requirements

Use structured events.

Every event should contain, where relevant:

```text
event_id
request_id
timestamp
source
event_type
severity
confidence
evidence
metadata
```

Do not encode important state changes only in logs.

If something should trigger replanning, it must be an explicit event.

Keep event names stable.

---

# 10. MCP Requirements

MCP may be used for:

- SQL
- RAG
- web/search
- memory
- chat database
- models
- verification
- enterprise APIs
- agent tools

MCP adapters must be isolated under `mcp/`.

Do not leak MCP-specific objects throughout the application.

Use internal normalized capability interfaces.

Required flow:

```text
ControlPlane
 ↓
Capability Request
 ↓
MCP Adapter
 ↓
MCP Server
 ↓
Capability
 ↓
Normalized Result
 ↓
Execution State / Event Bus
```

### Security

Never allow:

```text
Agent → MCP Tool → external action
```

without ControlPlane policy evaluation.

Required flow:

```text
Agent
 ↓
Proposed Tool Call
 ↓
ControlPlane Authorization + Risk
 ↓
ALLOW / MODIFY / HUMAN / BLOCK
 ↓
MCP Tool
 ↓
Post-action Verification
 ↓
Audit
```

---

# 11. Parallel Execution

Parallelism is a planning decision, not a default.

Use parallel execution when:

- tasks are independent
- dependencies permit concurrency
- policy allows it
- latency benefit is meaningful
- added cost is acceptable

Example:

```text
        Query
          ↓
     ControlPlane
          ↓
    ┌─────┼─────┐
    ↓     ↓     ↓
   SQL   RAG  Memory
    └─────┼─────┘
          ↓
     Evidence Merge
          ↓
       Reasoning
```

Do not fan out to every available capability.

The planner must determine the smallest useful set.

---

# 12. Evaluation Must Be Modular

Evaluators should be replaceable.

Potential interfaces:

```text
QualityEvaluator
FactualityEvaluator
GroundingEvaluator
ReasoningEvaluator
SafetyEvaluator
PrivacyEvaluator
PIIEvaluator
BiasEvaluator
SecurityEvaluator
CostEvaluator
LatencyEvaluator
ActionRiskEvaluator
ConsistencyEvaluator
```

Every evaluator should return structured results:

```text
score
confidence
issues
evidence
recommended_action
```

Do not hard-code one evaluation algorithm into the core architecture.

---

# 13. Failure Taxonomy Must Be Explicit

Distinguish:

```text
QUERY_FAILURE
DATA_FAILURE
RETRIEVAL_FAILURE
MODEL_FAILURE
REASONING_FAILURE
EVIDENCE_FAILURE
POLICY_FAILURE
TOOL_FAILURE
RESOURCE_FAILURE
```

Each failure class should eventually have one or more recovery strategies.

Do not use generic:

```text
ERROR
```

when a meaningful diagnosis is available.

---

# 14. Self-Healing Rules

Self-healing means:

> Detect failure → diagnose → choose bounded intervention → modify execution → verify.

Possible interventions:

```text
RETRY
REGENERATE
REROUTE
RETRIEVE
CHANGE_RETRIEVAL
CHANGE_MODEL
INCREASE_REASONING
DECREASE_REASONING
VERIFY
REPAIR
REDACT
ASK_CLARIFICATION
ABSTAIN
ESCALATE
HUMAN_REVIEW
BLOCK
ABORT
```

Never implement unbounded retry loops.

Every self-healing policy must respect:

- max retries
- cost budget
- latency budget
- risk threshold
- policy
- available evidence

---

# 15. The Product Must Produce the Better Answer

Do not build a system whose main output is:

> "The answer has a problem. You should use another model."

ControlPlane should act.

Preferred:

```text
Weak response
 ↓
Detected
 ↓
Reroute / Retrieve / Verify / Repair
 ↓
Improved response
 ↓
User
```

Recommendations may be shown in the dashboard, but the primary product behavior is **automatic improvement within policy**.

---

# 16. Trust Must Be Evidence-Backed

Never fabricate a precise trust probability unless the underlying method justifies it.

Prefer structured trust:

```text
TRUST: HIGH

Why:
 Supported by authorized sources
 Verification passed
 No significant disagreement
 Data is sufficiently current

Limitations:
 Q4 data unavailable
```

Low trust:

```text
TRUST: LOW

Why:
 Evidence insufficient
 Models disagree

Action:
Unsupported information was not presented as fact.
```

Trust must be traceable to evidence and evaluation outputs.

---

# 17. Abstention Is a Successful Outcome

The system must be allowed to say:

```text
ABSTAINED
```

when:

- evidence is insufficient
- required data is missing
- sources conflict
- authorization is unclear
- risk is too high
- human judgment is required
- the system cannot establish a trustworthy answer

Do not force every route to produce an answer.

---

# 18. Enterprise Data Principle

When authoritative enterprise data exists, use it rather than letting the LLM invent quantitative truth.

Examples:

```text
Revenue → SQL
Policy → Documents/RAG
Customer history → CRM/Chat DB
User preference → Memory
Current event → Web/API
Computation → Deterministic tool
Reasoning → Appropriate model
```

Do not use an LLM as the source of truth when a trustworthy deterministic source exists.

---

# 19. Agentic Action Control

For agents:

```text
PLAN
 ↓
PROPOSE ACTION
 ↓
CONTROLPLANE POLICY
 ↓
RISK
 ↓
ALLOW / MODIFY / HUMAN / BLOCK
 ↓
EXECUTE
 ↓
VERIFY
 ↓
AUDIT
```

Monitor the entire trajectory, not merely the final text.

Risk can compound over multiple turns.

---

# 20. Documentation Is a First-Class Product Artifact

Documentation is not optional.

Every meaningful code change must update documentation.

The goal is:

> **At any point, another developer—or the project owner—must be able to understand what exists, why it exists, how it works, what is incomplete, what has changed, and what should happen next without reconstructing the project from source code.**

---

# 21. Mandatory Project Documentation

Maintain these files at all times:

```text
AGENTS.md
PRODUCT_THESIS.md
docs/ARCHITECTURE.md

docs/PROJECT_STATE/
    CURRENT_STATE.md
    PROGRESS.md
    FUTURE_WORK.md
    DECISIONS.md
    BLOCKERS.md

docs/RESEARCH/
    README.md
    PAPER_INDEX.md

docs/ALGORITHMS/
    README.md

docs/CONTRACTS/
    README.md

docs/SCENARIOS/
    README.md

docs/TESTING/
    README.md
```

If a file/folder from this list does not exist, create it.

---

# 22. Documentation Rule for Every Major Folder

Every major source folder MUST contain a `README.md`.

Example:

```text
core/README.md
intelligence/README.md
mcp/README.md
capabilities/README.md
intervention/README.md
observability/README.md
learning/README.md
apps/dashboard/README.md
tests/README.md
```

Each folder README must state:

1. purpose
2. responsibilities
3. files/components inside
4. interfaces
5. dependencies
6. data flow
7. current implementation status
8. known limitations
9. next planned work
10. relevant tests
11. relevant research

If a new major folder is introduced, its README is mandatory in the same task.

---

# 23. Documentation Rule for Important Files

Every non-trivial source file must have a documentation record.

Preferred pattern:

```text
docs/FILE_SPECS/
    core/state/execution_state.md
    core/events/event_bus.md
    core/planning/planner.md
    intelligence/query/profiler.md
    intelligence/routing/model_router.md
    mcp/client/client.md
```

The documentation record must describe:

- file purpose
- public classes/functions
- inputs
- outputs
- side effects
- dependencies
- events emitted
- state modified
- error behavior
- tests
- algorithm currently used
- alternative algorithms considered
- known limitations
- future improvements

For trivial files, a folder README may be sufficient.

When in doubt, document the file.

---

# 24. Algorithm Documentation Is Mandatory

Every meaningful algorithm must have its own Markdown file.

Example:

```text
docs/ALGORITHMS/
    query_profiling.md
    risk_scoring.md
    model_routing.md
    data_routing.md
    adaptive_compute.md
    retrieval_quality.md
    factuality.md
    reasoning_quality.md
    safety.md
    privacy.md
    bias.md
    action_risk.md
    intervention_selection.md
    replanning.md
    trust_estimation.md
    learning_policy.md
```

Every algorithm document must contain:

```text
# Algorithm Name

## Status
PLANNED / BASELINE / EXPERIMENTAL / ADOPTED / DEPRECATED

## Problem

## Motivation

## Inputs

## Outputs

## Current Implementation

## Why This Method

## Research Basis

## Alternatives Considered

## Failure Modes

## Metrics

## Benchmark Results

## Known Limitations

## Next Experiment

## Open Questions
```

Never replace the research history just because a newer algorithm works better.

Record the evolution.

---

# 25. Research Paper Tracking

When a paper influences implementation, update:

```text
docs/RESEARCH/PAPER_INDEX.md
```

Record:

```text
Paper
Year
Problem
Main idea
Relevant ControlPlane block
What we borrowed
What we changed
Limitations
Implementation status
Experiment status
```

Also create a dedicated note for substantial papers:

```text
docs/RESEARCH/<paper_name>.md
```

Do not copy paper mathematics unnecessarily.

Focus on:

- concept
- architecture
- assumptions
- useful mechanism
- limitations
- relevance
- implementation implications

---

# 26. Current State Must Always Be Accurate

Maintain:

```text
docs/PROJECT_STATE/CURRENT_STATE.md
```

This is the authoritative description of:

- what actually works
- what is mocked
- what is partially implemented
- what is experimental
- what is not implemented

Never claim a feature is implemented when it only exists in architecture documentation.

Use explicit labels:

```text
IMPLEMENTED
PARTIAL
MOCKED
PLANNED
EXPERIMENTAL
BLOCKED
DEPRECATED
```

---

# 27. Progress Log

Maintain:

```text
docs/PROJECT_STATE/PROGRESS.md
```

After every meaningful task, update it.

Each entry should contain:

```text
Date
Task
What changed
Files changed
Tests run
Result
Known issues
Next step
```

Example:

```text
2026-08-25

Task:
Implemented Event Bus.

Changed:
- core/events/event_bus.py
- core/events/event_types.py

Tests:
14 passed

Known issue:
Persistence not implemented.

Next:
Connect Event Bus to ExecutionState.
```

Do not rewrite history.

Append entries chronologically.

---

# 28. Future Work

Maintain:

```text
docs/PROJECT_STATE/FUTURE_WORK.md
```

Separate:

```text
P0 — Required for prototype
P1 — Strong improvement
P2 — Research extension
P3 — Post-competition
```

Every new idea should go here before immediately becoming code.

Do not allow random ideas to enter the implementation without being classified.

---

# 29. Decision Log

Maintain:

```text
docs/PROJECT_STATE/DECISIONS.md
```

For important architecture decisions:

```text
Decision ID
Date
Decision
Context
Options
Chosen approach
Why
Trade-offs
Impact
```

Example:

```text
ADR-004

Decision:
Use Event Bus for route communication.

Rejected:
Direct route-to-route calls.

Reason:
Creates coupling and prevents dynamic replanning.
```

---

# 30. Blockers

Maintain:

```text
docs/PROJECT_STATE/BLOCKERS.md
```

Record:

- blocking bug
- missing dependency
- unavailable API
- research uncertainty
- unresolved architecture question
- dataset issue
- evaluation issue

Each blocker should contain:

```text
Problem
Impact
Possible solutions
Current owner
Next action
```

Remove or mark resolved blockers instead of silently deleting them.

---

# 31. Current File / Task Context

For active development, maintain:

```text
docs/PROJECT_STATE/CURRENT_TASK.md
```

It must contain:

```text
Current objective
Why it matters
Architecture block
Files being modified
Acceptance criteria
Current status
Known constraints
Tests required
Next action
```

Before beginning a new coding-agent session, update this file.

After finishing, update it.

This prevents context loss during Vibe coding.

---

# 32. Change Management Rule

Every coding task must follow:

```text
READ
 ↓
PLAN
 ↓
IMPLEMENT
 ↓
TEST
 ↓
DOCUMENT
 ↓
VERIFY
 ↓
UPDATE PROGRESS
```

Never:

```text
PROMPT
 ↓
GENERATE CODE
 ↓
DONE
```

---

# 33. Agent Task Protocol

When receiving a task:

## Step 1 — Understand

Read:

- AGENTS.md
- Product Thesis
- Architecture
- Current State
- Current Task
- relevant folder README
- relevant contracts
- relevant algorithm/research documents

## Step 2 — Identify impact

Determine:

```text
Which architecture block?
Which contracts?
Which files?
Which events?
Which state?
Which tests?
Which docs?
```

## Step 3 — Plan

Write a small implementation plan before modifying files.

## Step 4 — Implement

Make the smallest coherent change.

## Step 5 — Test

Run relevant tests.

## Step 6 — Document

Update:

- folder README
- file specification
- algorithm document
- progress
- current state if necessary
- decisions if necessary

## Step 7 — Report

Return:

```text
Implemented:
Files:
Tests:
Docs:
Architecture impact:
Known limitations:
Next step:
```

---

# 34. Coding-Agent Task Template

Every task given to a coding agent should follow this format:

```text
TASK

Objective:
<one specific objective>

Architecture block:
<exact block>

Relevant docs:
<paths>

Allowed changes:
<paths>

Do not change:
<protected paths>

Requirements:
1.
2.
3.

Acceptance criteria:
1.
2.
3.

Tests required:
1.
2.

Documentation required:
1.
2.

Expected final report:
- changed files
- tests
- documentation
- limitations
- next step
```

Agents should not infer broad architecture changes from a narrowly scoped task.

---

# 35. Do Not Let Vibe Coding Destroy the Architecture

The agent must never:

- introduce a new service without documenting it
- bypass ExecutionState
- bypass Event Bus for route communication
- bypass ControlPlane policy
- bypass MCP normalization
- put business logic only inside UI
- call models without telemetry
- silently swallow errors
- create untracked route transitions
- create undocumented algorithms
- remove tests to make code pass
- rewrite contracts silently
- change core architecture without approval

If the implementation requires an architectural change:

1. Stop.
2. Document the proposed change.
3. Add an ADR.
4. Update architecture documentation.
5. Then implement.

---

# 36. Never Hide Complexity in Prompts

Do not build the core architecture as one giant prompt.

Avoid:

```text
mega_prompt(
   classify +
   route +
   retrieve +
   evaluate +
   repair +
   decide
)
```

Prefer explicit components:

```text
QueryProfiler
Planner
Route
Evaluator
DecisionEngine
Replanner
Intervention
TrustEngine
```

Prompts may implement individual algorithms, but system behavior must remain observable and testable.

---

# 37. No Silent Fallbacks

If a capability fails, record it.

Bad:

```python
try:
    call_model()
except:
    call_other_model()
```

without telemetry.

Good:

```text
MODEL_FAILURE
 ↓
event
 ↓
ControlPlane
 ↓
fallback decision
 ↓
new route
```

Every fallback must be visible in history.

---

# 38. No Fake Confidence

Never output:

```text
confidence = 0.94
```

unless an actual method supports that interpretation.

If the system is heuristic, document it as:

```text
estimated confidence
heuristic risk score
evidence strength
```

Do not present heuristic values as calibrated probabilities.

---

# 39. No Unsupported Answers

If required information is unavailable:

```text
ABSTAIN
```

or:

```text
ASK_CLARIFICATION
```

or:

```text
ALTERNATE_SOURCE
```

Never silently fill missing enterprise information using model memory.

---

# 40. Deterministic Truth vs LLM Reasoning

When a deterministic system can provide authoritative truth, prefer it.

Examples:

```text
SQL → quantitative truth
Calculator → arithmetic
Database → records
Policy store → approved policy
API → live system state
LLM → reasoning / synthesis / language
```

Use LLMs where they add value.

Do not use LLMs merely because they are available.

---

# 41. Test Strategy

Tests must exist at four levels.

## Unit tests

Individual classes/functions.

## Contract tests

Verify component interfaces.

## Integration tests

Verify:

```text
Planner → Route → Event → Replanner
```

## Scenario tests

Full workflows:

```text
Public factual
Enterprise SQL
Insufficient RAG
Complex reasoning
Agentic high-risk action
```

---

# 42. Golden Dataset

Maintain a versioned evaluation set:

```text
data/evaluation/
```

Cover:

- public factual
- enterprise factual
- RAG
- insufficient RAG
- personal memory
- chat database
- SQL
- reasoning
- coding
- recommendation
- decision support
- sensitive data
- agentic actions
- missing context
- conflicting evidence
- model disagreement
- tool failure

Every major change should run against the golden set.

---

# 43. Baseline vs Research Evaluation

Do not claim an algorithm improves the system without measurements.

Compare:

```text
Baseline
vs
New algorithm
```

Metrics should include:

```text
quality
trustworthiness
hallucination/factuality
safety
recovery success
cost
latency
unnecessary escalation
abstention quality
route accuracy
```

When results are unknown, write:

```text
NOT YET MEASURED
```

rather than guessing.

---

# 44. Research-to-Code Workflow

For every research idea:

```text
Paper
 ↓
Research Note
 ↓
Hypothesis
 ↓
Algorithm Spec
 ↓
Baseline
 ↓
Implementation
 ↓
Experiment
 ↓
Metrics
 ↓
Result
 ↓
Decision
```

Example:

```text
Paper:
RouteLLM

Hypothesis:
A learned router can reduce expensive model calls while preserving quality.

Algorithm:
ModelRouter-v2

Experiment:
Golden Dataset v1

Result:
...

Decision:
Adopt / Reject / Further Test
```

This prevents research papers from becoming disconnected from the actual codebase.

---

# 45. Algorithm Experiment Rule

Never replace the current algorithm immediately.

Use:

```text
current/
candidate/
```

or feature flags.

Compare first.

Only promote after evaluation.

Document:

```text
Why candidate exists
How it is evaluated
What success means
What happened
```

---

# 46. Configuration Over Hard-Coding

Use configuration for:

- models
- capability registry
- policies
- thresholds
- budgets
- retries
- enabled evaluators
- enabled MCP servers

Do not scatter these values throughout code.

---

# 47. Observability Is Mandatory

Every model/tool/retrieval invocation should record, where applicable:

```text
request_id
step_id
capability
model
start_time
end_time
latency
estimated cost
token usage
status
error
```

Every route change must record:

```text
old route
new route
reason
triggering event
plan version
```

Every final response must connect to its execution trace.

---

# 48. Security Rules

Never commit:

- API keys
- passwords
- tokens
- private certificates
- credentials
- production customer data

Use:

```text
.env.example
```

and secret management.

MCP tools and agent actions must be authorization-controlled.

---

# 49. Documentation Quality Standard

Documentation must answer:

> What is this?
> Why does it exist?
> How does it interact with the rest of the system?
> What assumptions does it make?
> What is currently implemented?
> What is experimental?
> What can fail?
> How is it tested?
> What research supports it?
> What happens next?

Avoid documentation that merely repeats class names.

---

# 50. Automatic Documentation Checklist

Before completing a task:

```text
[ ] Code implemented
[ ] Tests added/updated
[ ] Folder README updated
[ ] File documentation created/updated
[ ] Algorithm documentation updated
[ ] Current State updated if needed
[ ] Progress updated
[ ] Future Work updated if new work was discovered
[ ] Decisions updated if architecture changed
[ ] Blockers updated if relevant
[ ] Research notes updated if relevant
```

If a checkbox is not applicable, explicitly state that in the final report.

---

# 51. Status Vocabulary

Use these exact status values:

```text
PLANNED
DESIGNED
BASELINE
IMPLEMENTED
INTEGRATED
EXPERIMENTAL
VALIDATED
ADOPTED
PARTIAL
MOCKED
BLOCKED
DEPRECATED
REJECTED
```

Do not use vague statuses such as:

```text
almost done
mostly working
probably works
```

---

# 52. Initial Project State

At repository bootstrap, the following concepts are already established at the design level:

- ControlPlane product thesis
- dynamic execution planning
- Query Intelligence
- dynamic execution graph
- shared state
- event-driven communication
- self-healing
- trust/evidence output
- history/auditability
- dashboard
- MCP capability fabric
- MCP as interoperability, not decision authority
- parallel capability routing
- model/data/tool routing
- agent/action governance
- algorithm replaceability
- research-driven improvement

Unless the repository proves otherwise, do not claim that these mechanisms are already implemented.

The architecture is designed; implementation status must be tracked separately.

---

# 53. Initial Development Priority

The foundation should be built in this order:

```text
1. Contracts
2. ExecutionState
3. Event Bus
4. Execution Graph
5. Planner Interfaces
6. History / Trace
7. Dashboard Skeleton
8. MCP Fabric
9. Basic Capabilities
10. Deterministic Baseline
11. Baseline Intelligence
12. Research Algorithms
13. Self-Healing
14. Learning
15. Evaluation / Optimization
```

Do not skip directly to sophisticated routing algorithms before the underlying execution and observability infrastructure is stable.

---

# 54. Final Agent Principle

The coding agent is an implementation collaborator, not the architect.

You must preserve:

```text
Architecture
Contracts
State
Events
Observability
Documentation
Research traceability
Tests
```

while iterating quickly.

The agent should optimize for:

> **fast implementation without loss of architectural clarity or experimental traceability.**

Every feature should leave behind:

```text
working code
tests
documentation
history
clear next step
```

---

# 55. Definition of Done for Any Feature

A feature is not complete when the code runs.

It is complete when:

```text
Code
 +
Tests
 +
Contract
 +
Documentation
 +
Observability
 +
Scenario coverage
 +
Progress entry
```

are all present.

For an algorithm:

```text
Algorithm code
 +
Algorithm MD
 +
Research reference
 +
Experiment
 +
Metrics
 +
Result
 +
Decision
```

For a major folder:

```text
Folder
 +
README.md
 +
Contracts
 +
Tests
 +
Status
 +
Future work
```

---

# 56. Final Rule

At every stage, the repository should tell the complete story:

```text
WHAT ARE WE BUILDING?
        ↓
PRODUCT_THESIS.md

HOW IS IT STRUCTURED?
        ↓
docs/ARCHITECTURE.md

WHAT EXISTS RIGHT NOW?
        ↓
CURRENT_STATE.md

WHAT HAVE WE DONE?
        ↓
PROGRESS.md

WHAT REMAINS?
        ↓
FUTURE_WORK.md

WHY DID WE MAKE THIS DECISION?
        ↓
DECISIONS.md

WHAT ALGORITHMS ARE WE USING?
        ↓
docs/ALGORITHMS/

WHAT RESEARCH SUPPORTS THEM?
        ↓
docs/RESEARCH/

HOW DO COMPONENTS COMMUNICATE?
        ↓
docs/CONTRACTS/

WHAT IS BEING IMPLEMENTED RIGHT NOW?
        ↓
CURRENT_TASK.md
```

**Never let the project become a state where the code is ahead of the documentation.**

The documentation and implementation should evolve together.


---

# 57. Scale and Reliability Requirements

The competition architecture assumes:

> **10,000 user interactions per week across the problem-statement use cases.**

This is a planning workload, not a reason to build unnecessary infrastructure.

The approximate average is:

```text
~1,430 interactions/day
~60 interactions/hour
~1 interaction/minute
```

However, agents must design for **bursty traffic**, not only averages.

One user interaction may generate multiple internal operations:

```text
query profiling
→ risk analysis
→ route selection
→ retrieval
→ model calls
→ evaluation
→ verification
→ intervention
→ replanning
→ tool calls
```

Therefore, internal events can be much more numerous than raw user requests.

## Scale Objective

The objective is:

> **Build a prototype whose interfaces and execution model can scale horizontally without introducing production-scale infrastructure that is unjustified for the competition workload.**

Do not claim scalability without measurement.

---

# 58. Critical vs Asynchronous Execution

Agents must distinguish between operations required before responding to the user and operations that can happen asynchronously.

### Keep on the critical path only when required

```text
query profiling
risk assessment
route selection
model execution
critical verification
intervention
replanning
final response
```

### Prefer asynchronous processing for

```text
dashboard aggregation
long-term analytics
route statistics
offline evaluation
benchmarking
historical analysis
learning signals
non-critical telemetry processing
```

Preferred pattern:

```text
USER
 ↓
Critical ControlPlane Path
 ↓
ANSWER
 ↓
Async Events
 ↓
Logs / Metrics / Dashboard / Evaluation / Learning
```

Do not make dashboard/analytics work unnecessarily block the user.

---

# 59. Statelessness

Where practical, ControlPlane orchestration workers should be stateless.

Preferred:

```text
Shared State / Stores
        ↑
        │
 ┌──────┼──────┐
 ↓      ↓      ↓
Worker Worker Worker
```

Do not keep critical execution state only in local process memory.

Persist state required for:

- routing
- replanning
- recovery
- audit
- execution trace
- human approval
- continuation of interrupted workflows

---

# 60. Event-Driven Scale

Do not tightly couple components through direct calls solely for logging, analytics, or secondary reactions.

Prefer:

```text
Component
 ↓
Structured Event
 ↓
Event Bus
 ├── Trace/History
 ├── Metrics
 ├── Dashboard
 ├── Evaluation
 └── Replanning
```

The event bus is a communication mechanism.

It is **not** the intelligence layer.

The ControlPlane still owns decisions.

---

# 61. Bounded Concurrency and Backpressure

Implement safeguards against burst traffic and runaway workflows.

Where appropriate:

```text
rate limiting
bounded concurrency
queueing
timeouts
cancellation
retry limits
circuit breakers
```

Never allow:

```text
evaluation → intervention → replan → evaluation → ...
```

to recurse indefinitely.

Every self-healing/replanning loop must have explicit bounds.

---

# 62. Cost and Latency Budgets

Treat cost and latency as first-class execution constraints.

Execution state should be able to track:

```text
latency_budget
latency_used
cost_budget
cost_used
model_calls
tool_calls
retrieval_calls
replan_count
```

Before adding a new model/evaluator/tool call to the critical path, document:

- why it is required
- expected latency
- expected cost
- fallback behavior
- whether it can be parallelized
- whether it can be asynchronous

---

# 63. Fast Path / Deep Path

Do not run maximum verification for every request.

### Fast Path

Use for simple, low-risk cases:

```text
light profiling
→ fast/cheap capability
→ lightweight verification
→ response
```

### Deep Path

Use for complex, uncertain, or high-impact cases:

```text
detailed profiling
→ risk analysis
→ richer capability plan
→ execution
→ evidence verification
→ potential escalation
→ replanning
→ final verification
```

The exact algorithms are not fixed yet.

The architecture must allow the decision to evolve.

---

# 64. Failure Isolation

Do not allow one dependency failure to unnecessarily crash the whole ControlPlane.

Where appropriate define degradation behavior for:

```text
model provider failure
retrieval failure
evaluator failure
cache failure
telemetry failure
dashboard failure
tool/API failure
```

For example:

```text
Model provider unavailable
→ alternate model/provider

Evaluator unavailable
→ alternate evaluator or bounded reduced verification

Dashboard unavailable
→ continue user path if safe

Cache unavailable
→ bypass cache if safe
```

Do not invent fallback behavior that the current policy does not permit.

---

# 65. Provider and Route Abstraction

Do not hard-code provider-specific implementations throughout routing logic.

Use abstractions such as:

```text
ModelProvider
Route
Capability
Evaluator
Intervention
```

The router should select a capability/model based on:

```text
query profile
risk
policy
cost
latency
capability
observed performance
```

It should not contain scattered provider-specific logic.

---

# 66. MCP and Scale

MCP can be used as the capability/interoperability layer for:

```text
SQL
RAG
Web/Search
Memory
Chat DB
Models
Verification
Enterprise APIs
Agent tools
```

But the rule remains:

> **DO NOT LET MCP BECOME THE BRAIN.**

Correct:

```text
ControlPlane
 ↓
decides what should happen
 ↓
MCP capability invocation
 ↓
result/event
 ↓
ControlPlane state
 ↓
replan if necessary
```

Incorrect:

```text
Query
 ↓
MCP
 ↓
MCP decides the complete workflow
```

MCP must not silently take ownership of:

- routing policy
- risk policy
- trust
- intervention
- replanning
- human escalation
- final authorization

---

# 67. Horizontal Scaling

The architecture should be able to evolve toward:

```text
                   Load Balancer
                        │
          ┌─────────────┼─────────────┐
          ↓             ↓             ↓
      CP Worker      CP Worker      CP Worker
          │             │             │
          └─────────────┼─────────────┘
                        ↓
                 Shared Services
```

Do not implement Kubernetes or a large distributed stack merely because it is associated with scale.

At the competition workload, prioritize:

```text
clean interfaces
Dockerized services
stateless workers where practical
persistent state
event-driven communication
observability
load tests
```

---

# 68. Technology Selection Rule

Possible queue/event technologies include:

```text
Redis Streams
NATS
RabbitMQ
Kafka
```

The agent must choose based on actual requirements.

Do **not** introduce Kafka merely to demonstrate "enterprise scalability."

Similarly, do not introduce Kubernetes unless actual testing or deployment requirements justify it.

---

# 69. Observability Requirements at Scale

Every meaningful execution should remain traceable.

Minimum fields should include:

```text
request_id
trace_id
timestamp
query
current_plan
plan_version
route
model_calls
retrieval_calls
tool_calls
evaluation_results
interventions
replans
latency
token_usage
estimated_cost
final_status
```

The dashboard must be able to answer:

```text
What happened?
Why?
Which route was used?
What failed?
What triggered intervention?
What changed?
Did the intervention help?
What did it cost?
```

---

# 70. Load Testing Requirement

Before making scalability claims, run measured tests.

At minimum test:

```text
normal workload
2× average workload
5× average workload
burst traffic
slow model/provider
model-provider failure
evaluator failure
queue backlog
replanning limits
cost-budget limits
long agent trajectory
```

Record:

```text
throughput
p50 latency
p95 latency
p99 latency
error rate
queue depth
model calls
tool calls
estimated cost
recovery rate
```

Never fabricate performance numbers.

Use:

```text
NOT MEASURED
```

until measured.

---

# 71. Required Scale Documentation

When implementing scale-related features, maintain:

```text
docs/ARCHITECTURE/
├── SCALE_ARCHITECTURE.md
├── RUNTIME_FLOW.md
├── EVENT_MODEL.md
├── FAILURE_AND_RECOVERY.md
├── PERFORMANCE_BUDGETS.md
└── CAPACITY_PLAN.md
```

At minimum:

```text
docs/ARCHITECTURE/SCALE_ARCHITECTURE.md
```

must reflect the current implementation.

If an agent changes the scale architecture, update the corresponding document in the same task.

---

# 72. Documentation Synchronization Rule

The scale requirement introduces a mandatory synchronization rule.

If a change affects:

```text
architecture
execution model
event model
state model
MCP integration
parallelism
scaling
latency
cost
failure recovery
```

the agent must update the relevant:

```text
PRODUCT_THESIS.md
docs/ARCHITECTURE.md
docs/ARCHITECTURE/SCALE_ARCHITECTURE.md
docs/PROJECT_STATE/CURRENT_STATE.md
docs/PROJECT_STATE/PROGRESS.md
docs/PROJECT_STATE/DECISIONS.md
```

Only update files that are genuinely impacted, but **do not leave the documentation stale**.

---

# 73. Scale-Aware Definition of Done

A feature that affects runtime behavior is not complete until:

```text
[ ] Code implemented
[ ] Tests added/updated
[ ] Failure behavior defined
[ ] Timeout behavior defined
[ ] Cost/latency impact considered
[ ] Observability added
[ ] Documentation updated
[ ] Progress updated
[ ] Current state updated if applicable
[ ] Architecture decision updated if architecture changed
```

For a new algorithm:

```text
[ ] Algorithm MD
[ ] Research basis
[ ] Baseline comparison
[ ] Experiment
[ ] Metrics
[ ] Result
[ ] Decision
```

---

# 74. Final Scale Principle

Do not optimize for hypothetical billions of requests.

Optimize for:

> **A clean, observable, reliable ControlPlane that comfortably addresses the competition's stated 10,000 interactions/week assumption and can evolve toward higher workloads without rewriting its core intelligence.**

Keep:

```text
INTELLIGENCE
=
routing
+ risk
+ evaluation
+ intervention
+ replanning
+ trust
```

separate from:

```text
INFRASTRUCTURE
=
API
+ workers
+ queues
+ storage
+ cache
+ telemetry
+ scaling
```

The coding agent must preserve this separation.

---

# 75. Research-Aligned Runtime Governance

This section adds runtime-governance rules derived from the current ControlPlane research direction. It **supplements** existing AGENTS.md rules and does not replace them.

The governing principle is:

> **For agentic execution, risk is a property of the trajectory, state, lineage, permissions, and cumulative actions — not only of an individual message or final response.**

The implementation must remain consistent with the Product Thesis and architecture: ControlPlane owns decision authority, while MCP remains a capability/interoperability fabric.

## 75.1 Trajectory-Level Governance

For any multi-step, tool-using, stateful, or agentic workflow, govern the **entire execution trajectory**.

A trajectory must be treated as a first-class control object containing, where applicable:

```text
trajectory_id
request_id
trace_id
session/conversation_id
principal/user identity
application identity
policy context
current risk state
current confidence state
current plan/version
execution steps
data touched
permissions acquired
models invoked
retrieval performed
tools invoked
external destinations
intermediate state changes
interventions
human approvals/overrides
final outcome
```

Do not assume that individually acceptable steps remain acceptable when composed.

Every runtime decision involving an agentic workflow must consider:

```text
current step
+
prior trajectory state
+
cumulative permissions
+
cumulative data exposure
+
cumulative action impact
+
new evidence
```

A final-response check is not a substitute for trajectory governance.

## 75.2 Trajectory Store + Execution Ledger

Maintain two related but distinct records:

```text
Trajectory Store
= the reconstructable execution state/history of the workflow

Execution Ledger
= the append-only record of consequential execution facts
```

The Trajectory Store should support recovery, replay, inspection, and replanning.

The Execution Ledger should record consequential facts such as:

```text
data accessed
permissions used/acquired
models invoked
tools called
actions proposed
actions authorized
actions executed
external destinations reached
policy decisions
risk/confidence decisions
interventions
human overrides
```

Ledger records must be append-only for audit purposes. Do not silently mutate historical facts.

A ledger entry should be attributable to:

```text
trajectory_id
event_id
timestamp
actor/source
action/capability
authorization context
policy version
result/status
evidence/reference
```

The ledger is a source of audit truth; it is not a replacement for the ControlPlane Decision Engine.

## 75.3 Behavioral Drift

Maintain a runtime **Behavioral Drift Score** for agentic or long-running trajectories where drift monitoring is justified.

The baseline score should prefer an interpretable weighted calculation over an opaque learned model.

Candidate signals include:

```text
tool-use velocity deviation
data-source deviation
action-sensitivity deviation
conversation/trajectory length deviation
monetary/value deviation
permission-scope deviation
external-destination deviation
```

The score is a governance signal, not a calibrated probability unless calibration has been demonstrated.

Drift should trigger reassessment of:

```text
risk
confidence
policy applicability
allowed capabilities
verification level
need for intervention
```

Do not automatically block on drift alone unless policy explicitly specifies that behavior.

## 75.4 Risk × Confidence Decision Policy

Do not reduce runtime governance to a single binary:

```text
PASS / BLOCK
```

Use a policy-controlled Risk × Confidence decision matrix with four primary outcomes:

```text
PASS
MONITOR
ESCALATE
BLOCK
```

Baseline policy:

```text
Low risk + high confidence
→ PASS

Low/moderate risk + uncertain confidence
→ MONITOR

High risk + high confidence
→ apply policy-specific controls; do not assume confidence makes risky actions safe

High risk + low confidence
→ ESCALATE or BLOCK
```

The exact thresholds are configuration, not architecture.

Risk and confidence must be separately represented because:

```text
high risk ≠ low confidence
low risk ≠ high confidence
```

Never present heuristic confidence as calibrated probability.

## 75.5 Defense-in-Depth

Use multiple independent control layers.

The baseline architecture should support:

```text
Deterministic rules
    ↓
Policy Engine
    ↓
Behavioral/trajectory risk signals
    ↓
Verifier/evaluator layer
    ↓
Decision Engine
    ↓
Intervention / Human / Execution
```

No single LLM, evaluator, or verifier should have unilateral authority to bypass all other safety controls.

A lower layer failing or disagreeing must not silently disable higher-level governance.

Independent layers should be observable so that post-incident analysis can determine:

```text
which layer fired
what it concluded
what evidence it used
what action followed
```

## 75.6 Shadow Mode

Runtime governance features that can materially affect production behavior should support:

```text
SHADOW
ENFORCE
```

In `SHADOW` mode:

```text
observe
score
evaluate
record
recommend
```

but do not change the user's execution path unless a separately configured hard safety boundary requires it.

Shadow results must still be written to the trajectory/audit records.

Every enforcement-capable control should make its mode explicit in configuration and telemetry.

Do not represent shadow observations as executed interventions.

## 75.7 Graceful Degradation

When a control, evaluator, verifier, model provider, retrieval system, or tool is unavailable, degrade capabilities **progressively** rather than failing open or immediately collapsing the whole workflow.

Possible degradation sequence:

```text
full capability
→ reduced capability
→ reduced autonomy
→ stronger verification
→ human review
→ safe abstention/block
```

Examples:

```text
Verifier unavailable
→ alternate verifier
→ bounded reduced verification
→ human review for high-impact cases
→ abstain/block if policy requires

Tool unavailable
→ alternate capability
→ draft-only mode
→ no external execution
```

Never invent a degraded path that violates application policy.

"Graceful degradation" does not mean "continue regardless of risk."

## 75.8 Partial Execution / Action State

Agent actions must be modeled as stateful transactions where possible.

At minimum, distinguish:

```text
PROPOSED
AUTHORIZED
EXECUTING
COMPLETED
PARTIALLY_COMPLETED
FAILED
BLOCKED
ABORTED
```

For actions that can be compensated or rolled back, record:

```text
rollback/compensation capability
rollback status
compensating action
```

Never claim rollback succeeded unless the external system confirms it.

If a workflow is blocked after an earlier irreversible action, preserve the resulting state and continue through a **compensation / containment / human-review** path rather than pretending the workflow is cleanly rolled back.

Partial execution must remain visible in the trajectory and Execution Ledger.

## 75.9 Multi-Agent Composition Risk

For multi-agent workflows, evaluate the **composition of actions**, not only each agent independently.

The ControlPlane must track at least:

```text
agent identity
parent/child relationship
shared state passed between agents
permissions inherited/transferred
data received from another agent
tools/actions proposed
cumulative action impact
```

Guard against composition failures such as:

```text
individually allowed actions combining into an over-limit result
permission laundering between agents
data obtained by one agent being exfiltrated by another
state transitions that bypass a policy boundary
```

No child agent should gain effective authority merely because another agent can access the capability.

The ControlPlane must evaluate aggregate trajectory state before allowing consequential composed actions.

## 75.10 Permission / Data Lineage

Every sensitive data access and consequential action should retain lineage sufficient to answer:

```text
Who/what requested it?
What data was accessed?
Under which permission?
For which purpose/trajectory?
Where did the data flow next?
Which agent/tool/model received it?
Which external destination received it, if any?
```

Permissions should be treated as trajectory state, not as a static property of an isolated agent call.

Do not allow permission laundering:

```text
Agent A
→ cannot access data directly

Agent B
→ accesses data

Agent B
→ passes sensitive result to Agent A

Agent A
→ sends data externally
```

The overall trajectory must still be evaluated against the originating authorization and data policy.

## 75.11 Agent Trajectory Intervention Points

The ControlPlane should expose explicit intervention points at meaningful state boundaries, not only at final output.

Minimum intervention opportunities:

```text
before planning
after initial profiling
before sensitive data access
before permission expansion
before tool invocation
before external write/action
after consequential tool result
after material risk/drift increase
after model/evaluator disagreement
before cross-agent state transfer
before final release
after failed/partial execution
```

At each intervention point, the decision engine may:

```text
CONTINUE
MONITOR
MODIFY
RETRIEVE
VERIFY
REPLAN
ESCALATE
HUMAN_REVIEW
BLOCK
ABORT
```

Do not implement a direct capability-to-capability bypass that skips required intervention points.

## 75.12 Fast Path / Deep Path Governance

Fast Path and Deep Path are runtime governance modes, not merely performance optimizations.

### Fast Path

Use when:

```text
low impact
low risk
high enough confidence
limited data sensitivity
no consequential external action
```

Expected pattern:

```text
light profiling
→ lightweight policy/risk checks
→ fast capability
→ lightweight verification
→ response
```

### Deep Path

Use when:

```text
high impact
material uncertainty
high sensitivity
complex reasoning
agentic execution
significant behavioral drift
multi-agent composition
consequential external action
```

Expected pattern:

```text
detailed profiling
→ risk/confidence analysis
→ capability/policy analysis
→ trajectory tracking
→ execution
→ evaluation
→ intervention/replanning
→ strong verification
→ human approval where required
```

The decision to move from Fast Path to Deep Path must be triggerable by new evidence during execution.

## 75.13 10,000 Interactions/Week Scale Requirements

The baseline workload assumption remains:

```text
10,000 interactions/week
≈ 1,430/day
≈ 60/hour on average
≈ 1/minute on average
```

Agents must design for burst traffic and for internal amplification caused by:

```text
profiling
risk checks
routing
retrieval
model calls
evaluation
verification
intervention
replanning
tool calls
```

A scale-aware implementation must therefore preserve:

```text
stateless workers where practical
persistent trajectory/execution state
bounded concurrency
backpressure
timeouts
retry limits
failure isolation
asynchronous telemetry
cost/latency budgets
horizontal evolution
load testing
```

The existing scale guide treats `50,000–100,000+` internal events/week as a plausible consequence of 10,000 user interactions before agentic amplification; this is a planning estimate, not a measured capacity claim.

Do not claim capacity, throughput, or reliability until measured.

At minimum, scale tests should include:

```text
normal load
burst load
2× average
5× average
provider/evaluator failure
queue backlog
long agent trajectory
replanning-limit behavior
cost-budget behavior
```

## 75.14 Documentation Synchronization

Any change to runtime governance must keep implementation and documentation synchronized.

Governance-affecting changes include:

```text
trajectory state
execution ledger
risk/confidence policy
drift scoring
shadow/enforcement mode
degradation behavior
action state
multi-agent controls
permission/data lineage
intervention points
fast/deep routing
runtime budgets
```

When such behavior changes, update all genuinely affected artifacts, including as applicable:

```text
AGENTS.md
PRODUCT_THESIS.md
docs/ARCHITECTURE.md
docs/ARCHITECTURE/SCALE_ARCHITECTURE.md
docs/PROJECT_STATE/CURRENT_STATE.md
docs/PROJECT_STATE/PROGRESS.md
docs/PROJECT_STATE/FUTURE_WORK.md
docs/PROJECT_STATE/DECISIONS.md
docs/RESEARCH/
docs/ALGORITHMS/
docs/CONTRACTS/
```

Do not mark a governance mechanism `IMPLEMENTED` merely because it exists in architecture documentation.

Architecture, contracts, implementation status, tests, and research notes must remain synchronized.

## 75.15 P0 / P1 / P2 Research Priorities

Use the repository's existing priority vocabulary and classify the research-aligned runtime-governance work as follows.

### P0 — Required for the prototype

Prioritize the smallest end-to-end governance spine:

```text
Trajectory Store + Execution Ledger
Risk × Confidence decision policy
Shadow Mode
Defense-in-depth
Permission/data lineage
Action state for partial execution
Trajectory intervention points
10,000-interaction/week scale foundations
```

P0 work must be implemented as a coherent runtime path before attempting research-heavy governance algorithms.

### P1 — Strong improvement

After the P0 spine is stable:

```text
Behavioral Drift Score
Multi-Agent Composition Risk controls
Graceful Degradation policies
Dynamic Fast Path / Deep Path transitions
Richer trajectory-level policy signals
```

P1 algorithms should be compared with the baseline using the existing evaluation framework before promotion.

### P2 — Research extension

Keep genuinely research-heavy ideas scoped and explicit rather than pretending they are production-ready:

```text
conformal prediction
adaptive test-time compute allocation
other learned/calibrated governance methods
chaos-engineering fault injection as a broader validation methodology
```

Do not move P2 work into the critical implementation path merely because it is novel.

## 75.16 Research-to-Code Workflow

For any new runtime-governance research idea, follow the existing research-to-code workflow:

```text
Research Reference / Paper
        ↓
Research Note
        ↓
Concrete ControlPlane Hypothesis
        ↓
P0/P1/P2 Classification
        ↓
Algorithm / Policy Specification
        ↓
Deterministic Baseline
        ↓
Candidate Implementation
        ↓
Golden Dataset / Scenario Test
        ↓
Offline or Controlled Experiment
        ↓
Metrics
        ↓
Result
        ↓
Decision
Adopt / Reject / Further Test
        ↓
Architecture + Contract + Status Update
```

The implementation must not jump directly from:

```text
paper → production code
```

Record:

```text
research basis
assumptions
what is novel
what is reused
baseline behavior
candidate behavior
success criteria
failure modes
measured results
known limitations
promotion decision
```

Never replace a stable baseline without comparison.

---
