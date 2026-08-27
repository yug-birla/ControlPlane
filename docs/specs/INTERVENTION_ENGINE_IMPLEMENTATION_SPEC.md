# ControlPlane.ai — Intervention Engine Implementation Specification

## Status

**Implementation Contract — ControlPlane Prototype / R2**

## Purpose

This document is the **implementation guide for the Intervention Engine**.

It defines how the coding agent must build the Intervention Engine from the existing ControlPlane architecture and contracts, including:

- intervention detection inputs
- intervention eligibility
- intervention selection
- intervention planning
- execution
- budgets
- policy enforcement
- trajectory awareness
- event emission
- replanning
- verification
- persistence
- auditability
- observability
- testing
- failure handling
- future algorithm replacement

This document is intentionally focused on **the Intervention Engine**.

It must not redesign the ControlPlane architecture, invent new storage systems, create unrelated microservices, or replace existing routing/evaluation contracts.

---

# 0. AUTHORITATIVE SOURCE ORDER

Before implementing anything, the coding agent MUST read these sources completely.

## Primary architecture and agent rules

1. `AGENTS_RESEARCH_ALIGNED_UPDATED.md`
2. `ControlPlane_High_Level_Architecture_OPTIMAL.md`
3. `RUNTIME_FLOW.md`
4. `EVENT_MODEL.md`
5. `FAILURE_AND_RECOVERY.md`
6. `TRAJECTORY_AND_LEDGER.md`
7. `SCALE_ARCHITECTURE_UPDATED(1).md`

## Existing implementation contracts

8. `FINAL_EVALUATION_GOVERNANCE_COMPONENT_SPEC.md`
9. `CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md`
10. `CONTROLPLANE_ROUTING_SYSTEM_SPEC.md`
11. `MODEL_AND_EVALUATION_DECISIONS.md`
12. `QDRANT_REDIS_DATA_CONTRACT.md`
13. `POSTGRES_SCHEMA.md`
14. `DATA_STORAGE_ARCHITECTURE.md`

## Data requirements

15. `CONTROLPLANE_DATA_WORK_INSTRUCTIONS.md`

## Older documents

16. `AGENTS_UPDATED.md`
17. `ControlPlane_High_Level_Architecture_UPDATED.md`
18. Older/non-canonical scale documents only for reference if needed.

Do not treat older architecture versions as competing sources of truth.

---

# 1. CORE ARCHITECTURAL RULE

The Intervention Engine is **not the ControlPlane brain**.

The architecture establishes:

```text
ControlPlane Core
    =
intelligence
+
state
+
policy
+
decision
+
replanning
```

The Execution Graph represents:

```text
what should happen
```

The Event Bus represents:

```text
what happened
/
what changed
```

The MCP Capability Fabric represents:

```text
how capabilities are discovered and invoked
```

The Intervention Engine is the component that **materializes a ControlPlane decision into a bounded execution change**.

It does NOT independently become the policy authority.

The evaluation/gov spec explicitly states that evaluators produce normalized observations and that ControlPlane combines those observations with policy, risk, confidence, impact, trajectory, budgets, and capability availability to decide what happens next.

---

# 2. WHAT THE INTERVENTION ENGINE IS

The Intervention Engine answers:

> **Given the current execution state and a ControlPlane decision, what controlled change should be applied to execution?**

It must transform:

```text
OBSERVATIONS
+
POLICY
+
RISK
+
CONFIDENCE
+
TRAJECTORY
+
BUDGETS
+
AVAILABLE CAPABILITIES
+
CURRENT PLAN
```

into:

```text
INTERVENTION DECISION
```

and then:

```text
EXECUTION CHANGE
```

followed by:

```text
POST-INTERVENTION VERIFICATION
```

The core loop is:

```text
OBSERVE
   ↓
EVALUATE
   ↓
DECIDE
   ↓
INTERVENTION ENGINE
   ↓
APPLY BOUNDED CHANGE
   ↓
REPLAN IF REQUIRED
   ↓
EXECUTE
   ↓
VERIFY
   ↓
MEASURE EFFECT
```

---

# 3. IMPORTANT DISTINCTION

Do not confuse:

```text
Evaluation
```

with:

```text
Intervention
```

Evaluation asks:

```text
What is happening?
How good is it?
How risky is it?
What evidence exists?
How confident are we?
```

Intervention asks:

```text
What controlled change should we make?
```

Replanning asks:

```text
What should the next execution graph look like?
```

Verification asks:

```text
Did the intervention actually improve the situation?
```

Therefore:

```text
Evaluator
   ↓
Observation
   ↓
Decision Engine
   ↓
Intervention Engine
   ↓
Replanner / Executor
   ↓
Verifier
```

Do not collapse all five responsibilities into one LLM call.

---

# 4. FORMAL INTERVENTION VOCABULARY

The current failure/recovery contract defines the formal intervention classes as:

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

These are the conceptual intervention types that the engine must support.

The existing PostgreSQL intervention schema currently lists:

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
```

while the failure/recovery model additionally defines:

```text
ABORT
```

Therefore:

> **Do not silently change the database schema.**

If implementation requires `ABORT` to be persisted as an `intervention_type`, create and document an explicit schema migration/change proposal before applying it.

The current event model also contains intervention event forms such as:

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

These are event/control representations and do not necessarily need to be stored as the same enum vocabulary as the database intervention taxonomy.

---

# 5. INTERVENTION TYPES — EXACT SEMANTICS

## 5.1 KEEP

Continue the current execution without a material change.

Use when:

- observed issue is harmless
- quality remains acceptable
- risk is within policy
- budgets remain sufficient
- no stronger intervention is justified

`KEEP` does not mean:

> "Ignore the failure."

It means:

> "The current trajectory remains acceptable."

---

## 5.2 VERIFY

Insert or strengthen verification.

Use when:

- uncertainty is material
- evidence exists but is limited
- a model switch needs confirmation
- an external action needs post-action verification
- a response is high-impact but still recoverable

Example:

```text
Answer generated
   ↓
confidence low
   ↓
VERIFY
   ↓
Verifier
```

---

## 5.3 RETRIEVE_MORE

Acquire additional evidence.

Use when:

- retrieval returned too little evidence
- evidence coverage is insufficient
- query ambiguity caused weak retrieval
- more information is likely to exist in authorized sources

Example:

```text
RAG
 ↓
INSUFFICIENT
 ↓
RETRIEVE_MORE
```

---

## 5.4 RERANK

Change evidence ordering without necessarily changing the data source.

Use when:

- corpus appears adequate
- retrieved candidates are likely relevant
- top selected evidence is poor
- reranking is cheaper than repeating retrieval

---

## 5.5 CHANGE_MODEL

Switch to a more suitable model.

Examples:

```text
Fast model
 ↓
reasoning uncertainty
 ↓
Strong reasoning model
```

or:

```text
Provider A unavailable
 ↓
Provider B
```

Selection must respect:

- capability
- risk
- policy
- cost
- latency
- remaining budget
- current trajectory
- current plan
- switching cost

---

## 5.6 INCREASE_COMPUTE

Increase reasoning or verification effort.

Examples:

```text
single generation
→ additional reasoning
```

or:

```text
light verification
→ stronger verification
```

Never increase compute without checking remaining cost and latency budgets.

---

## 5.7 DECREASE_COMPUTE

Reduce execution depth when quality requirements remain satisfied.

Examples:

```text
Deep verification
→ lightweight verification
```

or:

```text
Strong model
→ cheaper sufficient model
```

This intervention is particularly relevant to cost-aware adaptive execution.

---

## 5.8 CHANGE_DATA_SOURCE

Switch to an authorized alternative source.

Examples:

```text
RAG unavailable
→ SQL

stale document
→ authoritative structured data

web conflict
→ enterprise source
```

The source change must respect policy and data authorization.

---

## 5.9 REGENERATE

Generate a new answer/intermediate output without necessarily changing model or route.

Requirements:

- count as another model call
- consume budget
- record attempt number
- record reason
- do not repeat endlessly

Repeated generation of the same unsupported answer is not meaningful recovery.

---

## 5.10 REPAIR

Repair a locally recoverable problem.

Examples:

```text
malformed tool request
invalid input format
schema mismatch
transient connection problem
```

Repair should be deterministic where possible.

Do not use an LLM to repair something a deterministic transformation can safely fix.

---

## 5.11 REDACT

Remove or transform sensitive information.

Use for:

```text
PII
confidential information
policy-sensitive fields
unsafe content that can be safely removed
```

Preserve as much task utility as policy permits.

---

## 5.12 ASK_CLARIFICATION

Pause execution and ask the user for information that materially changes the solution.

Use when:

```text
missing information
ambiguous authorization
ambiguous intent
unclear target
unclear action scope
```

Do not guess when the missing information materially affects risk or correctness.

---

## 5.13 HUMAN_REVIEW

Pause automation and require attributable human judgment.

Typical reasons:

- high-impact action
- unresolved evidence conflict
- unclear authority
- privacy/security ambiguity
- policy exception
- external side effect
- recovery that would materially increase autonomy/risk

Human outcomes:

```text
APPROVE
REJECT
MODIFY
OVERRIDE
TIMEOUT
UNAVAILABLE
```

Human decisions must be appended to the history and must not erase the previous automated decision.

---

## 5.14 ABSTAIN

Produce a controlled terminal outcome when the system cannot meet the required standard.

Use when:

```text
evidence < required sufficiency
AND
safe recovery unavailable/exhausted
```

Abstention is not a failure of the ControlPlane.

It is a controlled governance outcome.

---

## 5.15 BLOCK

Prevent a proposed action/path.

Use when:

- policy prohibits it
- risk exceeds allowed bound
- security/privacy violation is present
- authorization fails
- action is impermissible

---

## 5.16 ABORT

Terminate remaining execution when continuation is no longer safe, valid, or economically justified.

Important:

```text
ABORT ≠ ROLLBACK
```

Do not claim rollback unless a real compensation/rollback capability exists.

---

# 6. INPUT CONTRACT

The Intervention Engine should receive a normalized `InterventionContext`.

Conceptually:

```json
{
  "request_id": "...",
  "trajectory_id": "...",
  "decision_id": "...",

  "current_plan": {
    "plan_id": "...",
    "plan_version": 3,
    "current_node_id": "..."
  },

  "observations": [],
  "evaluations": [],

  "risk_state": {},
  "confidence_state": {},
  "drift_state": {},

  "policy": {},

  "available_capabilities": [],

  "execution_state": {},

  "budgets": {
    "remaining_cost": 0,
    "remaining_latency": 0,
    "remaining_model_calls": 0,
    "remaining_tool_calls": 0,
    "remaining_replans": 0,
    "remaining_retries": 0
  },

  "partial_execution_state": {},

  "human_review_state": null
}
```

The actual schema should use existing ControlPlane contracts rather than inventing incompatible parallel structures.

---

# 7. REQUIRED INPUT DIMENSIONS

The Intervention Engine must evaluate at least:

## 7.1 Failure / trigger

Examples:

```text
MODEL_FAILURE
MODEL_DISAGREEMENT
RETRIEVAL_INSUFFICIENT
EVIDENCE_CONFLICT
HIGH_REASONING_UNCERTAINTY
HIGH_ACTION_RISK
PRIVACY_RISK
SAFETY_RISK
PII_DETECTED
BEHAVIORAL_DRIFT_HIGH
BUDGET_WARNING
VERIFICATION_FAILED
```

---

## 7.2 Risk

Use structured risk dimensions:

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

Do not reduce all risk to one scalar internally if the evaluator contracts provide richer information.

A scalar can be derived for policy thresholds where appropriate.

---

## 7.3 Confidence

Confidence may come from:

```text
model confidence
evaluator confidence
evidence sufficiency
model agreement
retrieval quality
verification
```

Do not fabricate precise probabilities.

If calibration is unavailable, use structured confidence categories or clearly labeled heuristic values.

---

## 7.4 Impact

Consider:

```text
information-only
low-impact
medium-impact
high-impact
critical external action
```

---

## 7.5 Trajectory

The recovery model requires trajectory-aware eligibility.

Example:

```text
one additional tool call
→ low risk

10 previous tool calls
+
sensitive data access
+
unresolved policy warning
→ same call may now be high risk
```

The Intervention Engine must therefore consume the current trajectory state, not just the current error.

---

## 7.6 Policy

The intervention must satisfy:

```text
policy permits intervention
```

Policy may constrain:

- capability
- data source
- model
- autonomy
- action
- human approval
- risk
- jurisdiction
- cost
- latency

---

## 7.7 Budgets

Required remaining state:

```text
remaining_cost_budget
remaining_latency_budget
remaining_model_call_budget
remaining_tool_budget
remaining_replan_budget
remaining_retry_budget
```

Do NOT base decisions only on original budgets.

---

## 7.8 Available capabilities

The engine must know what can actually be done.

Examples:

```text
RAG
SQL
web
memory
fast_model
strong_model
verifier
redaction
human_review
tool
```

Do not select a capability that is unavailable.

---

# 8. RECOVERY ELIGIBILITY GATE

Before selecting an intervention, run a recovery eligibility check.

The intervention is eligible only if applicable:

```text
policy permits it
AND
risk remains within allowed bound
AND
evidence exists or can plausibly be obtained
AND
remaining cost is sufficient
AND
remaining latency is sufficient
AND
retry/replan limits remain
AND
required capability is available
AND
external side effects are understood or safely containable
```

This gate must run **before** execution.

---

# 9. DECISION PIPELINE

Recommended structure:

```text
Trigger
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
Check recovery eligibility
  ↓
Generate candidate interventions
  ↓
Filter impermissible candidates
  ↓
Score/compare remaining candidates
  ↓
Select intervention
  ↓
Persist decision
  ↓
Emit INTERVENTION_TRIGGERED
  ↓
Apply intervention
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

---

# 10. CANDIDATE GENERATION

Candidate generation should be deterministic initially.

Example:

```text
IF retrieval insufficient:
    candidates = [
        RETRIEVE_MORE,
        RERANK,
        CHANGE_DATA_SOURCE,
        ASK_CLARIFICATION,
        ABSTAIN
    ]
```

```text
IF reasoning uncertainty:
    candidates = [
        VERIFY,
        CHANGE_MODEL,
        INCREASE_COMPUTE,
        REGENERATE,
        ABSTAIN
    ]
```

```text
IF privacy risk:
    candidates = [
        REDACT,
        CHANGE_DATA_SOURCE,
        HUMAN_REVIEW,
        BLOCK
    ]
```

```text
IF external high-impact action:
    candidates = [
        VERIFY,
        HUMAN_REVIEW,
        BLOCK,
        ABORT
    ]
```

These mappings are **candidate generators**, not final policy decisions.

Do not hard-code recovery inside individual capabilities.

---

# 11. CANDIDATE FILTERING

Reject an intervention before scoring if it violates:

```text
policy
risk limit
capability availability
budget
authorization
state consistency
side-effect constraints
```

Example:

```text
CHANGE_MODEL
```

must be rejected if:

```text
remaining latency < required model latency
```

or:

```text
model unavailable
```

or:

```text
policy does not permit provider
```

---

# 12. BASELINE INTERVENTION SCORING

The first implementation should be transparent and deterministic.

Use an interpretable score such as:

```text
intervention_score =
expected_quality_gain
+
risk_reduction
+
evidence_gain
+
recovery_probability
-
cost_penalty
-
latency_penalty
-
switch_penalty
-
risk_increase
```

Do not treat this as the final research algorithm.

It is the **baseline** against which learned intervention methods can later be compared.

Normalize/scale features before combining them.

Use configurable weights.

---

# 13. HARD CONSTRAINTS BEFORE SOFT SCORING

Never let a weighted score override a hard policy constraint.

Correct order:

```text
HARD GATES
    ↓
candidate filtering
    ↓
SOFT SCORING
    ↓
candidate ranking
    ↓
selection
```

Never:

```text
high_quality_score
>
policy violation
```

A forbidden action remains forbidden.

---

# 14. COST-AWARE INTERVENTION

The routing contract specifies expected cost and latency.

The Intervention Engine should use the same concept.

For a cascade:

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

Use **remaining** budget rather than initial budget.

Example:

```text
initial cost budget = 0.02
spent = 0.015
remaining = 0.005
```

An intervention expected to cost 0.01 is ineligible.

---

# 15. SWITCHING COST

The Intervention Engine must account for the cost of changing the current route.

Example:

```text
Current:
RAG → Fast

Candidate A:
continue current evidence → Strong

Candidate B:
Web → Strong
```

Candidate B may be more expensive because it discards useful work.

Track conceptually:

```text
switch_cost
```

Use:

```text
intervention_score
-
switch_cost
```

where applicable.

---

# 16. REMAINING BUDGET STATE

Never use static:

```text
max_cost
max_latency
```

alone.

Track:

```text
allocated
spent
reserved
remaining
```

For each:

```text
cost
latency
model calls
tool calls
replans
retries
```

The Intervention Engine must preserve budget for mandatory verification.

Do not spend all remaining resources on recovery and then discover verification cannot run.

---

# 17. REPLANNING BOUNDARY

The Intervention Engine does not need to create the full new graph itself if the architecture's Replanner owns that responsibility.

Recommended separation:

```text
Decision Engine
    ↓
Intervention Engine
    ↓
INTERVENTION_TRIGGERED
    ↓
Replanner
    ↓
PLAN_UPDATED
```

The Intervention Engine specifies:

```text
what should change
```

The Replanner determines:

```text
what the new execution graph looks like
```

Example:

```text
Intervention:
CHANGE_MODEL

Replanner:
replace node_4
from:
Qwen3 1.3B

to:
Grok reasoning
```

---

# 18. DIRECT EXECUTION VS REPLAN

Not every intervention requires a new plan version.

## Direct/local intervention

May include:

```text
VERIFY
REGENERATE
REDACT
REPAIR
```

when no graph topology changes.

## Replan-required intervention

Usually includes:

```text
CHANGE_MODEL
CHANGE_DATA_SOURCE
RETRIEVE_MORE
RERANK
INCREASE_COMPUTE
DECREASE_COMPUTE
HUMAN_REVIEW
```

where the execution graph or route materially changes.

When uncertain, prefer explicit plan versioning rather than silently mutating the current plan.

---

# 19. EVENT INTEGRATION

When an intervention is selected:

emit:

```text
INTERVENTION_TRIGGERED
```

with conceptual payload:

```text
intervention_type
trigger_event_id
reason
bounds
previous_step
expected_outcome
```

The event model explicitly defines `INTERVENTION_TRIGGERED` as being produced by the ControlPlane decision/intervention layer.

It does NOT itself mean that replanning occurred.

If replanning is needed:

```text
INTERVENTION_TRIGGERED
        ↓
REPLAN_TRIGGERED
        ↓
PLAN_UPDATED
```

This distinction must remain intact.

---

# 20. REQUIRED EVENT SEQUENCES

## Example A — Retrieval failure

```text
RETRIEVAL_INSUFFICIENT
        ↓
Decision
        ↓
INTERVENTION_TRIGGERED
(RETRIEVE_MORE)
        ↓
REPLAN_TRIGGERED
        ↓
PLAN_UPDATED
        ↓
RETRIEVAL_STARTED
        ↓
RETRIEVAL_COMPLETED
        ↓
EVALUATION_COMPLETED
        ↓
VERIFICATION_COMPLETED
```

---

## Example B — Model disagreement

```text
MODEL_DISAGREEMENT
        ↓
Decision
        ↓
INTERVENTION_TRIGGERED
(VERIFY / CHANGE_MODEL)
        ↓
possibly REPLAN_TRIGGERED
        ↓
new model / verifier
        ↓
verification
```

---

## Example C — High-risk action

```text
HIGH_ACTION_RISK
        ↓
Decision
        ↓
INTERVENTION_TRIGGERED
(HUMAN_REVIEW)
        ↓
HUMAN_REVIEW_REQUIRED
        ↓
APPROVE / REJECT / MODIFY / OVERRIDE
        ↓
continue or terminate
```

---

# 21. PERSISTENCE CONTRACT

The PostgreSQL schema already defines:

```text
interventions
```

with:

```text
id
request_id
trajectory_id
decision_id
intervention_type
target_node_id
reason
expected_effect
actual_effect
status
created_at
completed_at
```

Use this structure.

Do not create a parallel intervention database/table without architectural justification.

---

# 22. INTERVENTION STATUS

The implementation should use explicit lifecycle states.

Suggested minimum:

```text
PROPOSED
ELIGIBILITY_CHECKED
SELECTED
STARTED
APPLIED
FAILED
VERIFIED
PARTIALLY_COMPLETED
SUPERSEDED
CANCELLED
```

If existing PostgreSQL `status` conventions already exist elsewhere, reuse them rather than introducing incompatible names.

---

# 23. INTERVENTION RECORD

Every intervention record should conceptually contain:

```text
intervention_id
request_id
trajectory_id
decision_id
event_id
intervention_type

trigger
structured_reason

evidence_refs
policy_reference

pre_state
requested_change
post_state

expected_effect
actual_effect

cost_before
cost_after

latency_before
latency_after

risk_before
risk_after

confidence_before
confidence_after

verification_result

status
timestamps
```

The Trajectory/Ledger contract explicitly requires the intervention to be linked to:

```text
what triggered it
why it was selected
what changed
whether execution continued
whether a new plan resulted
whether it helped
```

---

# 24. ACTUAL EFFECT MUST BE MEASURED

Do not stop at:

```text
intervention = CHANGE_MODEL
```

Record:

```text
expected effect
```

and later:

```text
actual effect
```

Example:

```text
Expected:
quality ↑
latency ↑

Actual:
quality ↑
latency ↑
cost ↑
```

This becomes training/evaluation data.

It also enables:

```text
What interventions actually work?
```

rather than only:

```text
What interventions do we think work?
```

---

# 25. VERIFICATION AFTER INTERVENTION

Every material intervention must have an explicit verification policy.

Examples:

```text
CHANGE_MODEL
→ quality/factuality verification

RETRIEVE_MORE
→ evidence sufficiency verification

REDACT
→ privacy verification

REPAIR
→ capability success verification

HUMAN_REVIEW
→ human outcome verification

TOOL ACTION
→ post-action verification where policy requires
```

If verification itself fails:

```text
VERIFICATION_FAILED
```

then return to:

```text
Decision Engine
```

Do not automatically repeat the same intervention.

---

# 26. PREVENTING RECOVERY LOOPS

The engine must never do:

```text
failure
→ intervention
→ same failure
→ same intervention
→ same failure
→ ...
```

For every intervention track:

```text
attempt_number
failure_reason
previous_intervention
remaining_budget
previous_effect
```

Repeated failure should reduce eligibility for repeating the same intervention unless:

```text
new evidence
or
changed state
```

justifies it.

---

# 27. IDEMPOTENCY

Intervention execution must be idempotent where possible.

Examples:

```text
REDACT
REPAIR
RERANK
VERIFY
```

may often be repeatable.

But:

```text
tool action
external API
financial transaction
email
database write
```

may not be.

Before retrying an external action, check:

```text
was action already executed?
is operation idempotent?
can it be compensated?
does policy require human approval?
```

---

# 28. EXTERNAL SIDE EFFECTS

The Intervention Engine must treat side-effecting operations differently from information generation.

Information:

```text
generate answer
retrieve
rerank
verify
```

External side effect:

```text
send email
transfer money
modify CRM
delete record
publish content
```

For high-impact side effects:

```text
policy
+
action risk
+
authorization
+
trajectory
+
human approval where required
```

must be checked before execution.

If a side effect already occurred:

```text
record partial execution
```

Never claim:

```text
ROLLBACK_SUCCESS
```

unless actual compensation capability exists.

---

# 29. GRACEFUL DEGRADATION

The Intervention Engine must support progressive capability reduction where policy permits.

Example:

```text
FULL AGENT
    ↓
READ-ONLY
    ↓
DRAFT ONLY
    ↓
HUMAN APPROVAL
    ↓
BLOCK
```

Examples:

```text
can read, cannot write
can draft, cannot send
can inspect, cannot execute
```

This should be represented as a policy-compatible intervention rather than an ad hoc flag.

---

# 30. SHADOW MODE

Shadow mode must be supported.

In shadow mode:

```text
real AI execution
        ↓
ControlPlane observes
        ↓
Intervention engine simulates decision
        ↓
logs:
"would have changed model"
"would have required human"
"would have blocked"
```

But:

```text
NO ACTUAL ENFORCEMENT
```

The engine should produce the same decision record as enforcement mode where practical, with:

```text
mode = SHADOW
```

This allows measurement before enforcement.

---

# 31. HUMAN REVIEW

The Intervention Engine must integrate with the existing human-review contract.

Request:

```text
review_reason
review_scope
required_role
blocked_steps
```

Track human result:

```text
APPROVE
REJECT
MODIFY
OVERRIDE
TIMEOUT
UNAVAILABLE
```

A human override must never erase the automated intervention decision.

The final history should show:

```text
Automated decision
→ Human override
→ Result
```

---

# 32. DECISION PRIORITY

When multiple intervention signals exist simultaneously, do not simply select whichever evaluator fires first.

Use:

```text
critical policy/security constraints
        ↓
authorization constraints
        ↓
action risk
        ↓
privacy/security
        ↓
evidence sufficiency
        ↓
quality/reasoning
        ↓
cost/latency optimization
```

This ordering is a conceptual safety hierarchy.

The actual policy engine remains authoritative.

---

# 33. CONCURRENT FAILURES

If multiple failures occur:

```text
MODEL_DISAGREEMENT
+
PRIVACY_RISK
+
HIGH_ACTION_RISK
```

the engine must consider them jointly.

Do not independently apply:

```text
CHANGE_MODEL
+
REGENERATE
+
VERIFY
```

without checking whether privacy/action constraints already require:

```text
HUMAN_REVIEW
or
BLOCK
```

The failure/recovery contract explicitly requires simultaneous failures to be evaluated together.

---

# 34. INTERVENTION PLANNER — INITIAL IMPLEMENTATION

The first implementation should be deterministic and inspectable.

Recommended modules:

```text
InterventionEngine
├── TriggerNormalizer
├── EligibilityChecker
├── CandidateGenerator
├── PolicyFilter
├── BudgetFilter
├── RiskFilter
├── CandidateScorer
├── InterventionSelector
├── InterventionExecutor
├── ReplanCoordinator
├── VerificationCoordinator
└── OutcomeRecorder
```

These do NOT need to be microservices.

They can be modules/classes inside one ControlPlane package.

The existing governance specification explicitly recommends not creating separate services for quality, safety, privacy, bias, drift, risk, lineage, etc. merely for conceptual separation.

---

# 35. RECOMMENDED CODE PACKAGE STRUCTURE

Use the existing repository conventions if they already exist.

Otherwise, conceptually:

```text
controlplane/
├── intervention/
│   ├── __init__.py
│   ├── engine.py
│   ├── context.py
│   ├── candidates.py
│   ├── eligibility.py
│   ├── scoring.py
│   ├── selector.py
│   ├── executor.py
│   ├── outcomes.py
│   ├── policies.py
│   ├── budgets.py
│   ├── schemas.py
│   └── README.md
│
├── decision/
│   └── ...
│
├── replanning/
│   └── ...
│
├── evaluation/
│   └── ...
│
├── events/
│   └── ...
│
└── trajectory/
    └── ...
```

Do not create a new structure if the repository already has an established package structure. Adapt the responsibilities to the existing structure.

---

# 36. CORE INTERFACES

The coding agent should create stable interfaces.

## InterventionEngine

Conceptually:

```python
class InterventionEngine:
    def evaluate(
        self,
        context: InterventionContext
    ) -> InterventionDecision:
        ...
```

## EligibilityChecker

```python
class EligibilityChecker:
    def check(
        self,
        intervention: InterventionCandidate,
        context: InterventionContext
    ) -> EligibilityResult:
        ...
```

## CandidateGenerator

```python
class CandidateGenerator:
    def generate(
        self,
        context: InterventionContext
    ) -> list[InterventionCandidate]:
        ...
```

## Scorer

```python
class InterventionScorer:
    def score(
        self,
        candidate: InterventionCandidate,
        context: InterventionContext
    ) -> InterventionScore:
        ...
```

## Executor

```python
class InterventionExecutor:
    def apply(
        self,
        decision: InterventionDecision,
        context: InterventionContext
    ) -> InterventionResult:
        ...
```

## Replanner

The Intervention Engine must call the existing Replanner abstraction rather than creating its own planner implementation.

---

# 37. STABLE DATA CONTRACTS

Define models for:

```text
InterventionContext
InterventionCandidate
EligibilityResult
InterventionScore
InterventionDecision
InterventionExecution
InterventionOutcome
```

Each must be serializable for:

```text
PostgreSQL
events
logs
tests
dashboard
evaluation
```

Use versioning where the contract is externally persisted.

---

# 38. ALGORITHM REPLACEABILITY

The coding agent MUST separate:

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
Choose an intervention.

Baseline algorithm:
Rule-based candidate scoring.

Implementation:
CandidateScorer class.

Research hypothesis:
A learned policy may outperform rules.
```

Do not mix these.

The governance specification explicitly requires this separation.

---

# 39. ALGORITHM ROADMAP

## V0 — Required

```text
rules
+
policy
+
budgets
+
trajectory
+
candidate scoring
```

## V1 — Improve signals

```text
better confidence
better evidence scoring
better route capabilities
model disagreement
```

## V2 — Small learned intervention model

Only if the evaluation dataset is sufficient.

Potential candidates:

```text
gradient boosted trees
small MLP
compact encoder
small instruction model
```

Inputs might include:

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

## V3 — Learned policy

Potential research directions:

```text
contextual bandits
policy learning
reward modeling
```

## V4 — adaptive intervention policy

Only after sufficient execution history and stable evaluation.

Do not build V2–V4 before the V0 baseline is measurable.

---

# 40. TRAINING DATA

If the intervention engine eventually uses ML, it needs intervention examples.

The current data workstream explicitly targets:

```text
100–200 intervention cases
50–100 counterfactual cases
```

and human annotations should capture:

```text
preferred intervention
reason
expected effect
cost effect
latency effect
risk effect
```

Use this data only after schema and annotation quality are stable.

---

# 41. LOCAL ML REQUIREMENT

For the first intervention engine:

```text
LOCAL ML MODELS REQUIRED = 0
```

Use:

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
```

The governance contract explicitly establishes this general local-model policy.

If later evaluation shows a concrete gap, the **best first learned intervention component** is likely a small policy/classifier rather than a new large generative model.

Do not create one local model per intervention type.

---

# 42. FINE-TUNING POLICY

Use:

```text
V0
rules / pretrained / APIs
    ↓
V1
benchmark + human validation
    ↓
V2
small local model
    ↓
V3
fine-tuning if enough labeled data
    ↓
V4
continuous improvement from execution history
```

Do not fine-tune before:

- intervention dataset is stable
- labels are reviewed
- train/test split is protected
- baseline performance is measured
- failure cases are understood

---

# 43. RESEARCH PAPERS / RESEARCH AREAS TO STUDY

The Intervention Engine itself should be researched through several neighboring areas.

## A. LLM routing / model selection

Study:

- RouteLLM
- model cascading
- confidence-aware routing
- cost-aware routing

Use these primarily for:

```text
CHANGE_MODEL
INCREASE_COMPUTE
DECREASE_COMPUTE
```

---

## B. RAG evaluation

Study:

- RAGAS
- ARES

Use these for:

```text
RETRIEVE_MORE
RERANK
CHANGE_DATA_SOURCE
VERIFY
ABSTAIN
```

The current RAG contract already separates retrieval, RAG adequacy, generation, and factuality rather than collapsing them into one score.

---

## C. Agent runtime safety

Study:

- SafeAgent
- agent safety/runtime control literature
- tool-use safety
- indirect prompt injection

Use these for:

```text
HUMAN_REVIEW
BLOCK
RESTRICTED
ABORT
```

and trajectory-aware intervention.

---

## D. LLM-as-a-Judge / evaluator research

Study:

- MT-Bench / Chatbot Arena
- Prometheus
- ARES

Use evaluator outputs as **signals**, not automatic final policy.

---

# 44. INTERVENTION ENGINE DOES NOT NEED ITS OWN DATABASE

Use the existing PostgreSQL `interventions` table.

Store:

```text
decision
reason
expected effect
actual effect
status
timestamps
```

Use Qdrant only when an intervention itself needs semantic retrieval.

Use Redis for:

```text
short-lived state
event transport
rate limiting
cache
```

Do not create:

```text
intervention_db
intervention_vector_db
intervention_cache_db
```

without a measured requirement.

The storage contract explicitly fixes:

```text
PostgreSQL = authoritative structured state
Qdrant = vector retrieval
Redis = cache + event transport + rate limiting + short-lived coordination
```

---

# 45. POSTGRES TABLES THE ENGINE MUST USE

At minimum integrate with:

```text
requests
query_profiles
execution_states
plan_versions
decisions
interventions
evaluations
event_index
execution_ledger
```

The exact table/field names must follow `POSTGRES_SCHEMA.md`.

Do not create duplicate persistence models if existing tables already cover the information.

---

# 46. QDRANT USAGE

The Intervention Engine should not directly query Qdrant for everything.

Instead:

```text
Intervention
   ↓
CHANGE_DATA_SOURCE / RETRIEVE_MORE / RERANK
   ↓
Retrieval capability
   ↓
Qdrant
   ↓
Evidence
   ↓
Evaluation
```

The Qdrant contract specifies:

```text
enterprise_documents
conversation_search
memory
```

as the initial collections.

Use payload filters for authorized retrieval.

Do not treat Qdrant as authoritative state.

---

# 47. REDIS USAGE

Redis may be used for:

```text
event transport
short-lived locks
rate limiting
short-lived execution coordination
cache
```

Do not store the permanent intervention record only in Redis.

---

# 48. OBSERVABILITY

Every intervention must be traceable.

Minimum:

```text
request_id
trajectory_id
decision_id
event_id
intervention_id

intervention_type
trigger
reason

selected_candidate
rejected_candidates
policy
budget

before_state
after_state

expected_effect
actual_effect

execution_latency
additional_cost

verification_result
final_outcome
```

Dashboard must answer:

```text
What triggered this intervention?
Why was it selected?
Which alternatives were considered?
Why were they rejected?
What changed?
Did it help?
How much did it cost?
Did risk improve?
Did quality improve?
```

---

# 49. SECURITY / PRIVACY

The Intervention Engine handles potentially sensitive execution state.

Requirements:

- never store private chain-of-thought
- store structured rationale, not hidden reasoning
- redact sensitive fields according to application policy
- respect data access controls
- do not copy sensitive payloads unnecessarily into events
- use evidence references instead of duplicating sensitive content when possible
- preserve auditability without leaking confidential data

The existing governance specification explicitly prohibits storing private chain-of-thought.

---

# 50. FAILURE MODES OF THE INTERVENTION ENGINE

The engine itself can fail.

## Candidate generation failure

Fallback:

```text
safe default
+
HUMAN_REVIEW / ABSTAIN
```

depending on risk.

## Policy lookup failure

Do not proceed with an action whose authorization cannot be established.

Use:

```text
HUMAN_REVIEW
or
BLOCK
```

as appropriate.

## Budget state unavailable

Do not perform an unbounded expensive intervention.

Use a safe fallback.

## Replanner unavailable

Do not silently mutate route topology.

Possible:

```text
VERIFY
ABSTAIN
HUMAN_REVIEW
BLOCK
```

depending on risk.

## Intervention execution failure

Emit an event and return to ControlPlane decision handling.

Do not recursively invoke itself without bounds.

---

# 51. TESTING STRATEGY

The Intervention Engine needs multiple test layers.

## Unit tests

Test every intervention class:

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

where supported by current persistence contracts.

---

## Eligibility tests

Examples:

```text
policy forbids intervention
→ rejected

budget insufficient
→ rejected

capability unavailable
→ rejected

risk too high
→ rejected

human required
→ HUMAN_REVIEW
```

---

## Ranking tests

Given candidates:

```text
A cheap but weak
B expensive but strong
```

verify selection changes with:

```text
quality threshold
latency budget
cost budget
risk
```

---

## Trajectory tests

Verify that:

```text
same current failure
+
different previous trajectory
=
possibly different intervention
```

This is critical.

---

## Idempotency tests

Repeated intervention requests should not duplicate external actions.

---

## Failure injection

Test:

```text
provider failure
database failure
event failure
replanner failure
verification failure
```

---

# 52. EVALUATION DATA FOR THE INTERVENTION ENGINE

Use at least:

```text
100–200 intervention cases
50–100 counterfactual cases
```

The dataset should contain:

```text
query
initial route
execution state
failure
risk
confidence
available capabilities
candidate interventions
preferred intervention
reason
expected quality change
expected cost change
expected latency change
expected risk change
```

Human annotation should be used for the gold subset.

---

# 53. INTERVENTION ENGINE METRICS

Do not evaluate only intervention classification accuracy.

Measure:

## Decision quality

```text
intervention accuracy
```

## Recovery

```text
recovery success
recovery failure
```

## Safety

```text
unsafe intervention rate
false block rate
missed high-risk action rate
```

## Efficiency

```text
additional cost
additional latency
additional model calls
additional tool calls
```

## Replanning

```text
successful replan rate
replan failure rate
duplicate replan rate
```

## Outcome

```text
quality improvement
factuality improvement
grounding improvement
risk reduction
```

## Most important system metric

Compare:

```text
BASELINE
vs
CONTROLPLANE
```

on:

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
model calls
tool calls
```

The existing governance contract identifies this system-level comparison as the main KPI rather than optimizing evaluators independently.

---

# 54. P0 IMPLEMENTATION SCOPE

The first implementation must contain:

```text
[ ] InterventionContext
[ ] InterventionCandidate
[ ] EligibilityChecker
[ ] CandidateGenerator
[ ] PolicyFilter
[ ] BudgetFilter
[ ] RiskFilter
[ ] BaselineScorer
[ ] InterventionSelector
[ ] InterventionExecutor
[ ] PostgreSQL persistence
[ ] INTERVENTION_TRIGGERED event
[ ] Replanner integration
[ ] Verification integration
[ ] Actual-effect recording
[ ] Shadow Mode
[ ] basic human-review handoff
[ ] bounded retry/replan checks
[ ] unit/integration tests
```

---

# 55. P1 IMPLEMENTATION SCOPE

After P0 is stable:

```text
[ ] behavioral drift integration
[ ] learned intervention classifier/policy
[ ] better intervention ranking
[ ] trajectory-aware feature learning
[ ] counterfactual evaluation
[ ] policy optimization
[ ] learned recovery selection
[ ] richer graceful degradation
```

---

# 56. P2 / FUTURE

Do not make these dependencies of the competition prototype:

```text
[ ] reinforcement-learning intervention policy
[ ] advanced contextual bandits
[ ] fully learned replanner
[ ] adaptive test-time compute research
[ ] conformal intervention policies
[ ] formal compensation/rollback framework
[ ] sophisticated online learning
```

These may become research extensions after a robust baseline exists.

---

# 57. DETAILED IMPLEMENTATION PHASES

## Phase 1 — Contract

Before coding:

```text
read all source documents
confirm database schema
confirm event schema
confirm trajectory schema
confirm decision taxonomy
confirm route interfaces
```

Do not code if these conflict.

If conflict exists:

```text
STOP
DOCUMENT
ASK / PROPOSE MIGRATION
```

Do not silently reconcile.

---

## Phase 2 — Data Models

Implement:

```text
InterventionContext
Candidate
EligibilityResult
Score
Decision
Execution
Outcome
```

Add serialization tests.

---

## Phase 3 — Candidate Generation

Implement deterministic mappings from trigger to candidate interventions.

Do not invoke LLMs here initially.

---

## Phase 4 — Eligibility

Implement:

```text
policy
risk
confidence
trajectory
budgets
capabilities
side effects
```

filters.

---

## Phase 5 — Baseline Scoring

Implement:

```text
quality gain
risk reduction
evidence gain
recovery probability
cost
latency
switching cost
```

with configurable weights.

---

## Phase 6 — Decision Persistence

Persist:

```text
decision
intervention
reason
expected effect
policy
budget snapshot
```

---

## Phase 7 — Event Emission

Emit:

```text
INTERVENTION_TRIGGERED
```

with proper correlation and causation IDs.

---

## Phase 8 — Execute Intervention

Invoke the appropriate capability/replanner/human-review interface.

Never directly bypass architecture boundaries.

---

## Phase 9 — Verification

Record:

```text
verification started
verification result
actual effect
```

---

## Phase 10 — Replanning

Where graph topology changes:

```text
REPLAN_TRIGGERED
→ PLAN_UPDATED
```

with new plan version.

---

## Phase 11 — Shadow Mode

Run intervention decisions without enforcement.

Compare:

```text
would-have-intervened
vs
actual system behavior
```

---

## Phase 12 — Evaluation

Run the intervention dataset.

Compare:

```text
rules baseline
vs
alternative algorithms
```

---

# 58. ALGORITHM BENCHMARKING

When trying a new intervention algorithm:

```text
Baseline
+
New algorithm
```

must run on the same:

```text
training split
validation split
test split
challenge split
```

Do not tune directly on the challenge set.

Measure:

```text
quality
risk
recovery
cost
latency
false intervention
```

---

# 59. RESEARCH-TO-IMPLEMENTATION LOOP

For every future algorithm:

```text
PAPER
 ↓
RESEARCH NOTE
 ↓
HYPOTHESIS
 ↓
ALGORITHM SPEC
 ↓
BASELINE
 ↓
IMPLEMENTATION
 ↓
EXPERIMENT
 ↓
RESULTS
 ↓
ADOPT / REJECT
```

The coding agent must create/update:

```text
docs/ALGORITHMS/intervention/
```

with one MD per algorithm.

Suggested:

```text
RULE_BASED_INTERVENTION.md
LEARNED_INTERVENTION_BASELINE.md
COST_AWARE_INTERVENTION.md
BANDIT_INTERVENTION.md
```

only when those algorithms are actually implemented.

---

# 60. CODING-AGENT DOCUMENTATION REQUIREMENT

Every important Intervention Engine file must have documentation.

Minimum:

```text
intervention/
├── README.md
├── INTERVENTION_ENGINE.md
```

Every important implementation file should have a corresponding documentation reference.

The agent must update:

```text
CURRENT_STATE.md
PROGRESS.md
DECISIONS.md
FUTURE_WORK.md
```

when work changes the component.

---

# 61. DO NOT CREATE THESE

Do not create separate services such as:

```text
quality_service
reasoning_service
safety_service
privacy_service
bias_service
drift_service
risk_service
lineage_service
intervention_service
```

for the prototype unless measured load or a real ownership boundary requires it.

Prefer a modular ControlPlane package.

---

# 62. DO NOT DO THESE THINGS

Never:

- let an evaluator directly choose a new route
- let MCP decide the intervention
- let a capability call the re-planner directly
- hard-code all failure → intervention mappings inside capability implementations
- retry until success
- ignore remaining budgets
- ignore trajectory history
- hide partial execution
- claim rollback without rollback
- store private chain-of-thought
- create one LLM for every evaluator
- fine-tune before validating the baseline
- use one scalar score as the sole policy authority
- create infrastructure merely to appear scalable
- create duplicate databases
- create duplicate event systems
- create duplicate intervention persistence

---

# 63. FINAL END-TO-END CONTROL LOOP

The implemented engine must support this:

```text
USER REQUEST
     ↓
QUERY PROFILE
     ↓
INITIAL PLAN
     ↓
EXECUTION
     ↓
OBSERVATION
     ↓
EVALUATION
     ↓
RISK / CONFIDENCE / TRAJECTORY
     ↓
CONTROLPLANE DECISION
     ↓
┌────────────────────────────────────┐
│                                    │
│ KEEP                               │
│ VERIFY                             │
│ RETRIEVE_MORE                      │
│ RERANK                             │
│ CHANGE_MODEL                       │
│ INCREASE_COMPUTE                   │
│ DECREASE_COMPUTE                   │
│ CHANGE_DATA_SOURCE                 │
│ REGENERATE                         │
│ REPAIR                             │
│ REDACT                             │
│ ASK_CLARIFICATION                  │
│ HUMAN_REVIEW                       │
│ ABSTAIN                            │
│ BLOCK                              │
│ ABORT                              │
│                                    │
└────────────────────────────────────┘
     ↓
APPLY BOUNDED INTERVENTION
     ↓
REPLAN IF NEEDED
     ↓
EXECUTE
     ↓
VERIFY
     ↓
MEASURE ACTUAL EFFECT
     ↓
PERSIST / AUDIT / LEARN
```

---

# 64. Definition of Done

The Intervention Engine is not complete until:

```text
[ ] Intervention contracts implemented
[ ] Eligibility gate implemented
[ ] Candidate generation implemented
[ ] Policy filtering implemented
[ ] Budget filtering implemented
[ ] Risk filtering implemented
[ ] Baseline candidate scorer implemented
[ ] Intervention selector implemented
[ ] PostgreSQL intervention persistence integrated
[ ] Event emission integrated
[ ] Trajectory linkage integrated
[ ] Replanner integration implemented
[ ] Verification integration implemented
[ ] Human review integration implemented
[ ] Shadow mode supported
[ ] Partial execution represented
[ ] Retry/replan bounds enforced
[ ] Idempotency considered
[ ] External side-effect safeguards implemented
[ ] Actual effect recorded
[ ] Unit tests implemented
[ ] Integration tests implemented
[ ] Failure tests implemented
[ ] Evaluation dataset connected
[ ] Metrics implemented
[ ] Dashboard trace available
[ ] Documentation updated
[ ] Progress/state/decisions updated
```

---

# 65. Final Design Principle

The Intervention Engine should not simply answer:

> **"Something went wrong."**

It should implement:

> **"Something changed in the execution state. Given the trajectory, policy, evidence, risk, confidence, available capabilities, and remaining cost/latency budgets, this is the safest and most useful bounded change we can make. We will then verify whether that change actually improved the outcome."**

The Intervention Engine is therefore the bridge between:

```text
EVALUATION
```

and:

```text
SELF-HEALING CONTROL
```

without becoming a second brain.

It should remain:

```text
deterministic where possible
model-assisted where useful
policy-constrained
trajectory-aware
budget-aware
observable
replaceable
testable
```

and it must preserve the ControlPlane architectural authority over decisions and replanning.
