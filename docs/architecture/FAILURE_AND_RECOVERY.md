# ControlPlane.ai — Failure and Recovery Model

**Status:** Architecture Contract

**Scope:** Competition Prototype / R2, with production evolution boundaries

**Subsystem:** Failure Detection + Diagnosis + Intervention + Replanning + Recovery Governance

**Related contracts:**
- `PRODUCT_THESIS.md`
- `docs/ARCHITECTURE.md`
- `docs/ARCHITECTURE/TRAJECTORY_AND_LEDGER.md`
- `docs/ARCHITECTURE/EVENT_MODEL.md`
- `docs/PROJECT_STATE/DECISIONS.md`

---

## 1. Purpose

ControlPlane is not complete when it detects that an answer, execution step, capability, or action has failed.

The purpose of this document is to define the formal failure taxonomy and bounded recovery model for the ControlPlane runtime. The model turns failure from a terminal observation into a governed execution state that can be diagnosed, acted upon, and verified.

The governing recovery loop is:

```text
detect
  ↓
diagnose
  ↓
choose intervention
  ↓
replan
  ↓
execute again / continue safely
  ↓
verify
  ↓
finish / degrade / escalate / abstain / block / abort
```

This is consistent with the product thesis: ControlPlane dynamically evaluates execution, changes the execution strategy when the current path becomes inappropriate, and seeks the best trustworthy outcome rather than merely reporting that a model failed.

Self-healing is therefore defined as **bounded, policy-aware recovery**, not unrestricted retrying.

### Non-negotiable recovery principles

1. **Never retry until success.** Every retry, model call, tool call, replan, and recovery branch consumes a bounded budget.
2. **Never force an answer when evidence is insufficient.** Abstention is a valid successful control outcome.
3. **Never claim rollback unless the system actually has rollback capability.** Blocking a later step does not reverse an earlier side effect.
4. **Represent partial execution explicitly.** A trajectory can end partially executed even when the user-visible result looks complete.
5. **High-impact actions may require human approval.** Recovery must not silently increase autonomy.
6. **Recovery decisions are logged and explainable.** The decision trace records what happened, why the intervention was selected, what policy applied, and what happened next.
7. **Graceful degradation is a first-class outcome.** The system does not reduce every failure to PASS or BLOCK.
8. **The ControlPlane remains authoritative.** Capabilities and evaluators report observations; they do not decide their own recovery path.

---

## 2. Failure Taxonomy

ControlPlane uses the following primary failure taxonomy:

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

The taxonomy describes the **cause or condition** that makes the current execution path invalid, unsafe, unreliable, or inefficient. A single trajectory may contain multiple failures and may move between failure classes during recovery.

### 2.1 QUERY_FAILURE

The request cannot be safely or correctly interpreted.

Examples:
- ambiguity that materially changes the required action
- missing required parameters
- contradictory instructions
- unclear target, scope, authority, or intended outcome
- an initial query profile that becomes invalid after new evidence

Typical response:

```text
ASK_CLARIFICATION
REPLAN
ABSTAIN
BLOCK
```

### 2.2 DATA_FAILURE

Required information does not exist, is unavailable, is stale beyond the allowed tolerance, or cannot be accessed under the current authorization context.

Examples:
- required dataset absent
- source inaccessible
- source is outside the allowed data scope
- required field is missing
- source freshness is below policy requirements

Typical response:

```text
CHANGE_DATA_SOURCE
RETRIEVE_MORE
ABSTAIN
HUMAN_REVIEW
```

### 2.3 RETRIEVAL_FAILURE

The required information may exist, but the selected retrieval strategy failed to retrieve adequate evidence.

Examples:
- low recall
- poor query formulation
- incomplete top-k evidence
- poor ranking
- retrieval source mismatch
- evidence coverage below threshold

Typical response:

```text
RETRIEVE_MORE
RERANK
CHANGE_DATA_SOURCE
VERIFY
ABSTAIN
```

### 2.4 MODEL_FAILURE

The selected model or provider is unsuitable for the current task or execution state.

Examples:
- provider outage or timeout
- model capability mismatch
- model quality below policy threshold
- context handling failure
- invalid or malformed model response
- repeated model disagreement on a task requiring stronger reliability

Typical response:

```text
CHANGE_MODEL
INCREASE_COMPUTE
REGENERATE
VERIFY
ABORT
```

### 2.5 REASONING_FAILURE

The execution requires more, different, or better-verified reasoning than the current path produced.

Examples:
- unresolved multi-step reasoning uncertainty
- unsupported causal conclusion
- failed numerical reasoning
- plan incompleteness
- internal inconsistency detected by an evaluator

Typical response:

```text
INCREASE_COMPUTE
CHANGE_MODEL
REGENERATE
VERIFY
REPLAN
```

### 2.6 EVIDENCE_FAILURE

Evidence is insufficient, contradictory, stale, inaccessible, or otherwise inadequate to justify the intended conclusion or action.

Examples:
- conflicting sources
- unsupported claim
- missing evidence for a high-impact assertion
- stale evidence where freshness is required
- evidence coverage gap

Typical response:

```text
RETRIEVE_MORE
RERANK
CHANGE_DATA_SOURCE
VERIFY
ABSTAIN
HUMAN_REVIEW
```

### 2.7 POLICY_FAILURE

The requested or proposed execution cannot be fulfilled under the active policy context.

Examples:
- unauthorized data access
- prohibited action
- action risk exceeds allowed autonomy
- policy requires human approval
- required verification level cannot be satisfied

Typical response:

```text
REDACT
HUMAN_REVIEW
BLOCK
ABORT
ABSTAIN
```

A policy failure is not necessarily a system malfunction. It may be the correct governance decision.

### 2.8 TOOL_FAILURE

An invoked tool, API, database, enterprise service, or capability invocation failed.

Examples:
- timeout
- authentication failure
- schema mismatch
- rate limit
- malformed tool output
- service unavailable
- post-action verification failure

Typical response:

```text
REPAIR
CHANGE_DATA_SOURCE
RETRY
CHANGE_MODEL
ABORT
```

### 2.9 RESOURCE_FAILURE

The current route violates or is projected to violate execution budgets or resource constraints.

Examples:
- latency budget exhausted or near exhaustion
- cost budget exhausted or near exhaustion
- tool/model call budget exhausted
- concurrency capacity unavailable
- recovery is no longer economically justified

Typical response:

```text
DECREASE_COMPUTE
KEEP
ABSTAIN
BLOCK
ABORT
```

---

## 3. Failure Severity

Severity describes the **consequence and urgency** of the failure, not merely how unusual the event is.

A failure severity level should be determined from the current query profile, trajectory state, evidence, permissions, actionability, external impact, and policy.

| Severity | Meaning | Default control posture |
|---|---|---|
| `S0_INFO` | Non-failure observation or harmless deviation | KEEP; continue monitoring |
| `S1_LOW` | Local failure with low user or system impact and a bounded safe recovery path | Self-heal when budget and policy permit |
| `S2_MEDIUM` | Material quality, evidence, capability, or resource degradation | Recover with verification; consider degradation |
| `S3_HIGH` | High-risk failure, evidence conflict, authorization concern, or potentially consequential action | Pause; require stronger verification and possibly human review |
| `S4_CRITICAL` | Unsafe, unauthorized, security/privacy-critical, or irreversible external consequence risk | BLOCK or ABORT unless an explicit approved recovery path exists |

Severity must not be treated as immutable. A new event can increase or reduce severity.

### Severity escalation examples

```text
S1 retrieval gap
  ↓ repeated inadequate retrieval
S2 evidence failure
  ↓ decision-support impact + unresolved conflict
S3 high-impact evidence conflict
  ↓ proposed external action
S4 critical action-risk condition
```

Severity should be recalculated after material interventions and after new evidence arrives.

---

## 4. Failure Detection

Failure detection converts observations into structured failure events. Detection must operate over the **trajectory**, not only the latest model output.

Potential detection signals include:

```text
model output
retrieval adequacy
source/evidence coverage
model disagreement
policy evaluation
risk state
confidence
verification results
tool status
action result
provider status
latency consumption
cost consumption
retry count
replan count
human checkpoint state
trajectory state transitions
observability health
```

### 4.1 Detection sources

| Detection source | Example signal |
|---|---|
| Capability | timeout, malformed output, unavailable source |
| Model | uncertainty, malformed response, disagreement |
| Retrieval | insufficient evidence, low coverage, poor ranking |
| Evaluator | factuality/grounding/reasoning/safety failure |
| Policy engine | unauthorized or disallowed execution |
| Runtime | budget threshold or timeout |
| Event bus | explicit failure or state-transition event |
| Trajectory state | repeated failure, escalating risk, partial execution |
| Human | override, rejection, correction, escalation |
| Observability | missing telemetry, stale heartbeat, inconsistent trace |

### 4.2 Detection contract

A material failure should be represented as a structured event rather than only a log message.

Conceptually:

```text
failure_event = {
    event_id,
    trajectory_id,
    request_id,
    timestamp,
    failure_type,
    severity,
    confidence,
    detection_signal,
    evidence_refs,
    affected_node,
    affected_capability,
    policy_context,
    budget_state,
    external_side_effect_state
}
```

The Event Bus communicates what happened. It does not decide which recovery path should execute.

---

## 5. Failure Diagnosis

Detection answers **“what signal occurred?”** Diagnosis answers **“what actually explains the deviation?”**

Diagnosis should distinguish correlation from root cause where practical.

### 5.1 Diagnosis hierarchy

```text
Observed deviation
      ↓
Failure candidate(s)
      ↓
Evidence collection
      ↓
Root-cause confidence
      ↓
Impact assessment
      ↓
Recovery eligibility
```

### 5.2 Multiple simultaneous failures

A trajectory may legitimately have more than one active failure:

```text
RETRIEVAL_FAILURE
        +
EVIDENCE_FAILURE
        +
RESOURCE_FAILURE
```

The ControlPlane should not force a single diagnosis when the evidence supports multiple contributing causes.

### 5.3 Failure of the answer vs failure of the execution path

These must be distinguished.

**Failure of the answer:**

```text
The execution completed, but the produced answer is not trustworthy enough.
```

**Failure of the execution path:**

```text
One or more steps failed or became inappropriate, but another safe path may exist.
```

A failed path does not necessarily imply a failed task.

### 5.4 Failure of the capability

The capability itself is unavailable or unsuitable.

Example:

```text
Model provider unavailable
```

This is different from:

```text
The model returned a weak answer despite being available
```

### 5.5 Failure of the governance decision

The execution can be technically successful while the ControlPlane's governance decision is incorrect or incomplete.

Examples:
- allowing an action that should have required human approval
- escalating a low-risk task unnecessarily
- selecting an intervention inconsistent with policy
- failing to account for cumulative trajectory risk

Governance-decision failures are especially important for later evaluation and learning because the underlying capability may have behaved correctly.

### 5.6 Failure of an external side effect

An external action is a separate failure domain.

Examples:
- email sent when it should not have been
- transaction partially completed
- record updated but downstream synchronization failed
- external API accepted the request but post-action verification failed

The ledger must distinguish:

```text
proposed
authorized
attempted
accepted
executed
verified
partially executed
failed
unknown
```

---

## 6. Recovery Eligibility

Not every failure is eligible for autonomous recovery.

A recovery candidate is eligible only when all applicable constraints are satisfied:

```text
policy permits the intervention
AND
risk remains within the permitted bound
AND
required evidence exists or can plausibly be obtained
AND
remaining cost budget is sufficient
AND
remaining latency budget is sufficient
AND
retry / replan limits remain
AND
necessary capability is available
AND
external side effects are understood or safely containable
```

### 6.1 Recovery decision classes

| Condition | ControlPlane posture |
|---|---|
| Low risk + clear bounded recovery | Autonomous recovery |
| Moderate risk + strong evidence | Recovery + verification |
| High risk + reversible path | Recovery only if policy explicitly allows it |
| High risk + ambiguous evidence | HUMAN_REVIEW or ABSTAIN |
| Critical policy/security/action violation | BLOCK or ABORT |
| No evidence and no safe recovery path | ABSTAIN |
| Budget exhausted | Graceful degradation, ABSTAIN, BLOCK, or ABORT depending on actionability |
| External side effect already occurred | Record partial execution; compensate only if an actual compensation capability exists |

### 6.2 Recovery eligibility is trajectory-aware

A recovery that is safe in isolation may become unsafe after cumulative execution.

For example:

```text
One additional tool call → low risk

Ten prior tool calls + sensitive data access + unresolved policy warning
→ same tool call may now exceed trajectory risk
```

Recovery eligibility therefore considers cumulative state, not only the current node.

---

## 7. Intervention Classes

The formal intervention vocabulary for this model is:

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

### 7.1 KEEP

Continue the current plan without a material change because the observed issue does not justify intervention or the detected deviation is harmless.

`KEEP` does not mean “ignore the failure.” It means the current trajectory remains acceptable under policy and budgets.

### 7.2 VERIFY

Add or strengthen verification before continuing or releasing the result.

Use when:
- uncertainty is material but recoverable
- evidence exists but confidence is limited
- a model switch or repair needs confirmation
- an external action requires post-action verification

### 7.3 RETRIEVE_MORE

Acquire additional evidence using the current or compatible retrieval capability.

### 7.4 RERANK

Change ranking or evidence ordering when the retrieval corpus is likely adequate but the selected evidence is poor.

### 7.5 CHANGE_MODEL

Switch to a model with a more suitable capability, reliability profile, or cost/latency trade-off.

### 7.6 INCREASE_COMPUTE

Increase reasoning depth, verification effort, or bounded inference budget when justified by task complexity and remaining budgets.

### 7.7 DECREASE_COMPUTE

Reduce execution depth or choose a cheaper/faster route when quality requirements remain satisfied and the current path is overspending resources.

### 7.8 CHANGE_DATA_SOURCE

Switch to an alternative authorized source when the current source is unavailable, stale, inaccessible, or inadequate.

### 7.9 REGENERATE

Generate a new answer or intermediate result without necessarily changing the underlying model or route.

Regeneration must still count against retry/model-call limits.

### 7.10 REPAIR

Repair an execution artifact or capability interaction that is known to be locally recoverable.

Examples:
- normalize an invalid input shape
- repair a malformed tool request
- recover a transient connection
- correct a deterministic schema mismatch

### 7.11 REDACT

Remove or transform data that violates privacy, security, or policy constraints while preserving as much task utility as possible.

### 7.12 ASK_CLARIFICATION

Pause execution and obtain information required to continue safely.

This is preferred over guessing when the missing information materially changes the result or action.

### 7.13 HUMAN_REVIEW

Pause autonomous progression and require an attributable human decision.

Typical triggers:
- high-impact action
- unresolved evidence conflict
- policy exception request
- privacy/security ambiguity
- critical external side effect
- recovery that would materially increase autonomy or risk

### 7.14 ABSTAIN

Return a controlled outcome that explicitly states the system cannot support the requested answer or action to the required standard.

Abstention is the correct outcome when:

```text
evidence < required sufficiency
AND
safe recovery is unavailable or exhausted
```

### 7.15 BLOCK

Prevent a proposed execution path or action from proceeding because policy or risk makes continuation impermissible.

### 7.16 ABORT

Terminate the current trajectory or remaining execution because continuing is no longer safe, valid, or economically justified.

`ABORT` does not imply rollback.

---

## 8. Replanning

Replanning is the mechanism by which ControlPlane changes the execution graph after a material failure or new evidence.

The initial plan is provisional. Every material plan change should be represented as a new plan version.

### 8.1 Replanning inputs

A replanning decision may use:

```text
current trajectory state
failure diagnosis
new evidence
current policy
risk/confidence state
capability availability
model profiles
retrieval state
partial execution state
remaining latency budget
remaining cost budget
remaining retry budget
human approval state
external side-effect state
```

### 8.2 Replanning rules

1. Do not hard-code failure-to-route mappings inside capabilities.
2. Do not replan solely because a failure event occurred; assess whether recovery is worthwhile and permitted.
3. Do not discard prior plan versions or prior attempts.
4. Material replans must be logged with structured rationale.
5. A replan must preserve already-executed state and respect dependencies.
6. A replan must not silently repeat an external side effect.
7. A replan must not increase autonomy beyond the active policy.
8. Verification requirements may increase after failure; they should not silently decrease to bypass a failed check.

### 8.3 Replanning pattern

```text
Plan v1
  ↓
Failure / new evidence
  ↓
Diagnosis
  ↓
Intervention decision
  ↓
Plan v2
  ↓
Execute remaining / replacement nodes
  ↓
Verify
```

---

## 9. Retry Limits

Retries are controlled execution attempts, not an implicit loop.

Every retry should have:

```text
attempt_number
node_execution_id
failure_reason
intervention_id
remaining_budget
result
```

### Retry principles

- A retry must not overwrite the previous attempt.
- Repeated retries against the same failure mode should reduce recovery eligibility unless new evidence justifies them.
- Transient infrastructure failures may be more retryable than semantic or policy failures.
- Policy failures should not be retried merely to obtain a different outcome.
- Repeated model generation of materially similar unsupported content is not meaningful recovery.
- Tool retries must consider idempotency and external side effects.

### Required runtime limits

The recovery policy exposes at least:

```text
max_replans
max_model_calls
max_tool_calls
max_latency
max_cost
max_risk
max_retry_count
```

These are policy inputs. Concrete numeric defaults are configuration decisions, not hard-coded architecture guarantees.

---

## 10. Cost Budgets

Recovery consumes resources. The controller must reason about **remaining** budget, not only total planned budget.

Conceptually:

```text
remaining_cost
=
allocated_cost
-
actual_cost
-
reserved_recovery_cost
```

### Cost-aware recovery rules

- Prefer low-cost interventions when they have adequate expected value.
- Do not invoke an expensive model solely because a cheaper route failed unless the expected improvement justifies the spend and policy permits it.
- Do not spend the remaining budget on recovery that cannot leave sufficient budget for mandatory verification.
- If cost budget is exhausted, choose an allowed degradation, abstention, human route, block, or abort outcome.

The intended optimization target is not raw recovery rate. It is recovery value subject to quality, risk, cost, and latency constraints.

---

## 11. Latency Budgets

Recovery must operate within the request's latency contract.

Conceptually:

```text
remaining_latency
=
allocated_latency
-
elapsed_latency
-
reserved_verification_latency
```

The controller should account for:

```text
model inference
retrieval
reranking
tool latency
evaluator latency
human wait time
replanning overhead
verification
```

### Latency rules

- Low-risk queries should preserve fast paths.
- Expensive recovery should only occur when the expected quality/risk improvement justifies the delay.
- Human review can exceed the normal interactive latency budget only when policy allows asynchronous or paused execution.
- A route that can no longer meet the user's allowed latency should not continue blindly; it should degrade, abstain, escalate, block, or abort according to policy.

---

## 12. Risk Limits

Risk is multi-dimensional and trajectory-aware.

Relevant dimensions include:

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

Recovery may not increase risk merely to recover completion.

### Risk rules

1. An intervention must have a permitted maximum post-intervention risk.
2. High-impact actions require stronger governance than information-only responses.
3. Risk-increasing interventions require explicit policy support.
4. Unresolved privacy/security/policy failures may make autonomous recovery ineligible even when quality could be improved.
5. A quality improvement that creates unacceptable action risk is not a valid recovery.

Conceptually:

```text
allowed recovery
iff
post_recovery_risk ≤ policy_limit
```

---

## 13. Human Escalation

Human escalation is a control mechanism, not a system failure.

Human review should be considered when:

- the action is high impact
- evidence materially conflicts
- authority or consent is unclear
- policy requires approval
- an external side effect already occurred and requires a decision
- privacy/security implications are unresolved
- autonomous recovery would materially increase risk or autonomy
- the system cannot establish a sufficiently trustworthy recovery path

### Human decision outcomes

```text
APPROVE
REJECT
MODIFY
OVERRIDE
TIMEOUT
UNAVAILABLE
```

Human decisions must be attributable and must not erase the preceding automated decision trace.

---

## 14. Abstention

Abstention is a controlled terminal outcome when the system cannot meet the required trust, evidence, policy, or safety standard.

The system should abstain rather than:

```text
invent evidence
repeat unsupported reasoning
silently downgrade policy
hide a partial action
pretend verification succeeded
claim a rollback that did not occur
```

### Trust-aware abstention

A useful abstention should communicate, at the appropriate user-visible level:

```text
what could not be established
why the available evidence was insufficient
what was attempted
what was not executed
whether additional information or human review is needed
```

---

## 15. Blocking

Blocking is the authoritative prevention of a prohibited or unacceptably risky path.

Blocking applies when:

- policy prohibits the action
- security/privacy constraints are violated
- risk exceeds the permitted maximum
- required human approval is absent
- evidence is materially insufficient for a high-impact action
- recovery limits have been exhausted and continuation is unsafe

Blocking must be represented in the trajectory and ledger.

A block does not mean the whole request was meaningless. The system may still provide a safe informational response or partial completion when policy permits.

---

## 16. Graceful Degradation

ControlPlane should degrade the **execution contract** rather than fail catastrophically whenever safe.

Possible outcomes include:

```text
FULL_SUCCESS
SUCCESS_WITH_LIMITATIONS
DEGRADED_ANSWER
PARTIAL_EXECUTION
AWAITING_HUMAN
ABSTAINED
BLOCKED
ABORTED
FAILED
```

Examples:

### Retrieval degradation

```text
Full enterprise evidence unavailable
→ use smaller authorized evidence set
→ disclose limitation
→ reduce confidence
```

### Model degradation

```text
Preferred reasoning model unavailable
→ use supported lower-cost model
→ add verification if permitted
→ disclose reduced confidence where material
```

### Verification degradation

Mandatory verification unavailable:

```text
Do not silently treat unverified output as verified.
→ use an approved weaker path only if policy permits
→ otherwise abstain / human review / block
```

---

## 17. Partial Execution

Partial execution is a first-class trajectory state.

Example:

```text
READ record
   completed

PREPARE action
   completed

EXTERNAL ACTION
   accepted by external system

POST-ACTION VERIFICATION
   failed

LATER ACTION
   blocked
```

The final record must distinguish:

```text
what was proposed
what was authorized
what was attempted
what actually executed
what external side effect occurred
what was verified
what remained pending
what was blocked
what recovery followed
```

The final outcome may therefore be `PARTIALLY_EXECUTED` even when a response is still returned.

A response that appears successful must not erase the fact that an action was partially executed or that verification failed.

---

## 18. Rollback / Compensation Concept

Rollback and compensation are distinct capabilities and must not be conflated with blocking or aborting.

### 18.1 Rollback

Rollback means returning a system state to an earlier state using an actual supported rollback mechanism.

The architecture must not assume rollback exists merely because the execution graph can stop.

### 18.2 Compensation

Compensation means performing a separate corrective action intended to mitigate or reverse an already completed external effect.

Examples conceptually:

```text
create resource
  → compensation: delete resource
```

or:

```text
send incorrect update
  → compensation: issue corrective update
```

Compensation is itself an external action and therefore requires the same authorization, risk analysis, logging, verification, and possible human approval as the original action.

### 18.3 No false rollback assumption

The following is invalid:

```text
later step blocked
→ therefore earlier external action was rolled back
```

The correct representation is:

```text
earlier external action occurred
→ later step was blocked
→ current external state is known / unknown
→ compensation capability exists / does not exist
→ human review required / not required
```

---

## 19. Failure Isolation

Failures should be isolated to the smallest safe execution scope.

Isolation levels may include:

```text
node
attempt
route
parallel branch
capability
provider
agent
sub-agent
workflow
trajectory
```

### Isolation rules

- A single failed parallel branch should not automatically invalidate independent successful branches.
- A provider outage should not necessarily invalidate the entire trajectory if an equivalent capability exists.
- A failed sub-agent should not automatically authorize another sub-agent to perform a prohibited action.
- Shared state changes must be evaluated for cross-branch effects before continuing.
- High-risk failures should propagate to the trajectory governance layer even when the local node appears recoverable.

---

## 20. Provider Failure

Provider failure is a class of model or capability availability failure.

Examples:

```text
provider timeout
provider unavailable
rate limit
invalid provider response
provider authentication failure
provider capacity failure
```

Recovery options may include:

```text
RETRY          if transient and bounded
CHANGE_MODEL   if another provider/model is authorized
DECREASE_COMPUTE if the task can be safely simplified
ABORT          if no acceptable provider path exists
```

Provider-specific recovery logic must remain behind normalized capability interfaces.

A provider failure should not cause the ControlPlane to lose the ability to explain why the route changed.

---

## 21. Retrieval Failure

Retrieval failures should distinguish retrieval-system failure from evidence insufficiency.

```text
RETRIEVAL_FAILURE
= retrieval mechanism did not produce adequate results

EVIDENCE_FAILURE
= the available evidence is insufficient/contradictory even after retrieval
```

Typical progression:

```text
retrieve
→ insufficient evidence
→ RETRIEVE_MORE / RERANK / CHANGE_DATA_SOURCE
→ verify evidence
→ answer / degrade / abstain
```

---

## 22. Model Failure

Model failure includes capability mismatch, malformed output, provider failure, or reliability below the required threshold.

The controller should prefer a **reasoned model switch** over random model cycling.

Model switching should use model capability profiles where available, including:

```text
capabilities
latency class
cost class
known strengths
known weaknesses
observed performance
```

---

## 23. Evaluation Failure

Evaluation failure is distinct from model failure.

It may mean:

```text
evaluator unavailable
evaluator timeout
evaluator output malformed
evaluator confidence too low
evaluators disagree
verification cannot establish the required property
```

When evaluation itself fails, the system must not silently treat the result as “verified.”

Possible responses:

```text
RETRY evaluator
CHANGE evaluator
VERIFY with another method
HUMAN_REVIEW
ABSTAIN
BLOCK
```

Evaluator disagreement should be represented as a first-class observation when it materially changes the decision.

---

## 24. Tool Failure

Tool failures may be transient, deterministic, authorization-related, or side-effect-related.

Before retrying a tool, the controller should assess:

```text
idempotency
external-side-effect risk
current authorization
remaining tool-call budget
provider state
```

A tool call that may have succeeded externally but returned an error is especially important. The system must represent the external result as `UNKNOWN` when it cannot establish whether the side effect occurred.

It must not blindly retry a potentially non-idempotent action.

---

## 25. Policy Failure

Policy failure is a governance constraint, not a capability defect.

Policy failures should not normally be “retried.” They should trigger one of:

```text
REDACT
ASK_CLARIFICATION
HUMAN_REVIEW
ABSTAIN
BLOCK
ABORT
```

A route may change only if the new route is also policy-compliant.

---

## 26. Data Failure

Data failure should distinguish:

```text
DATA_MISSING
DATA_INACCESSIBLE
DATA_STALE
DATA_INVALID
DATA_OUT_OF_SCOPE
DATA_INCOMPLETE
```

Recovery may use an alternate authorized source, clarification, or a reduced claim scope. It must never fabricate missing data.

---

## 27. Reasoning Failure

Reasoning failure occurs when the produced reasoning or decision is not reliable enough for the task's required standard.

Signals include:

```text
inconsistency
unsupported inference
failed verification
causal uncertainty
numerical inconsistency
multi-step plan failure
model disagreement on a high-impact conclusion
```

Recovery may increase computation, switch models, retrieve evidence, add a verifier, or replan.

More computation is not inherently better; it is permitted only when expected improvement exceeds its cost, latency, and risk.

---

## 28. Evidence Conflict

Evidence conflict is a special evidence failure requiring explicit conflict representation.

```text
Source A → claim X
Source B → claim not-X
```

The system should not silently select one source merely because it is more convenient.

Possible strategies:

```text
RERANK
RETRIEVE_MORE
CHANGE_DATA_SOURCE
VERIFY
INCREASE_COMPUTE
HUMAN_REVIEW
ABSTAIN
```

The selected strategy should depend on source authority, recency, provenance, task impact, and policy.

---

## 29. Privacy / Security Failure

Privacy and security failures have a higher control priority than ordinary answer-quality failures.

Examples:

```text
PII exposure
unauthorized data access
secret leakage
cross-tenant leakage
unsafe tool authorization
prompt-injection-induced privilege misuse
sensitive-data exfiltration
```

Potential interventions:

```text
REDACT
BLOCK
ABORT
HUMAN_REVIEW
CHANGE_DATA_SOURCE
```

The controller must not trade privacy or security for answer completion unless an explicit policy permits the exact trade-off.

---

## 30. Agentic / Action Failure

Agentic workflows introduce external side-effect risk.

The governing pattern is:

```text
Agent proposes action
      ↓
Action risk assessment
      ↓
Policy
      ↓
ALLOW / MODIFY / HUMAN / BLOCK
      ↓
Execute
      ↓
Post-action verification
      ↓
Audit
```

Failure types include:

```text
wrong tool
wrong parameters
wrong target
wrong authorization scope
wrong sequence
unnecessary action
irreversible action
failed escalation
partial action
unknown action outcome
```

High-impact action failures should be treated as at least `S3_HIGH` and may require `S4_CRITICAL` handling depending on the consequence.

---

## 31. Multi-Agent Composition Failure

A set of individually acceptable agent outputs can compose into an unacceptable trajectory.

Examples:

```text
Agent A retrieves restricted information
Agent B transforms it
Agent C sends it externally
```

or:

```text
Agent A recommends action
Agent B assumes recommendation is verified
Agent C executes recommendation
```

The ControlPlane must govern the composition through shared trajectory state, permissions/data lineage, cumulative risk, and action authorization.

A multi-agent component must not use another agent as an indirect path around policy.

---

## 32. Behavioral Drift

Behavioral drift is a change in observed behavior of a model, provider, capability, evaluator, data source, or policy pack that causes prior routing/recovery assumptions to become less reliable.

Possible signals:

```text
rising failure rate
rising intervention rate
new failure clusters
quality degradation
latency degradation
cost increase
model/provider version change
retrieval distribution shift
policy/rule-pack change
```

Drift should affect future model/capability profiles and routing decisions. It should not retroactively rewrite historical execution records.

---

## 33. Observability Failure

Observability failure occurs when ControlPlane cannot reliably observe the execution state needed to govern it.

Examples:

```text
missing event
missing correlation ID
stale telemetry
broken trace linkage
missing tool result
missing decision record
inconsistent state between execution and ledger
```

Observability failure is itself a governance concern because the system may no longer be able to prove what happened.

For high-risk actions, loss of required observability should be treated as a reason to pause, block, abort, or escalate according to policy.

For low-risk work, asynchronous telemetry loss may permit graceful degradation when the execution state required for safe continuation remains available.

---

## 34. Budget Exhaustion

Budget exhaustion is a normal terminal recovery condition, not necessarily a system defect.

Budgets include:

```text
replans
model calls
tool calls
latency
cost
risk allowance
```

When a budget is exhausted:

```text
Do not silently exceed it.
Do not enter an unbounded retry loop.
Do not downgrade mandatory policy checks.
```

Select the safest allowed final state:

```text
KEEP / DEGRADED ANSWER
ABSTAIN
HUMAN_REVIEW
BLOCK
ABORT
```

---

## 35. Recovery Telemetry

Recovery decisions must be measurable and reconstructable.

At minimum, recovery telemetry should capture:

```text
recovery_id
trajectory_id
request_id
failure_event_id
failure_type
severity
diagnosis_confidence
intervention_type
decision_id
plan_version_before
plan_version_after
risk_before
risk_after
confidence_before
confidence_after
cost_before
cost_after
latency_before
latency_after
retry_count_before
retry_count_after
replan_count_before
replan_count_after
model_calls_before
model_calls_after
tool_calls_before
tool_calls_after
human_required
human_outcome
partial_execution_state
external_side_effect_state
verification_result
recovery_outcome
recovery_success
recovery_failure_reason
structured_rationale
policy_reference
```

### Recovery outcome categories

```text
RECOVERED
RECOVERED_WITH_LIMITATIONS
DEGRADED
AWAITING_HUMAN
ABSTAINED
BLOCKED
ABORTED
FAILED_TO_RECOVER
UNKNOWN
```

### Core recovery metrics

The evaluation system should be able to compute at least:

```text
failure detection precision
failure detection recall
false intervention rate
missed failure rate
intervention accuracy
recovery success rate
recovery failure rate
average replans per trajectory
average extra model calls
average extra tool calls
recovery cost overhead
recovery latency overhead
abstention rate
human escalation rate
block rate
partial-execution rate
verification failure rate
provider failure recovery rate
```

The metrics must not be optimized independently. A higher recovery rate is not automatically better if it increases risk, cost, or latency beyond policy.

---

## Failure → Recovery Reference Table

The following matrix is conceptual. Exact thresholds and intervention permissions are policy/configuration decisions.

| Failure type | Detection signal | Possible interventions | Low-risk allowance | High-risk allowance | Human required? | Final fallback |
|---|---|---|---|---|---|---|
| `QUERY_FAILURE` | ambiguity, missing parameter | `ASK_CLARIFICATION`, `REPLAN`, `ABSTAIN` | Ask / replan | Prefer clarification; no unsafe guess | When impact or authority is unclear | `ABSTAIN` |
| `DATA_FAILURE` | missing/inaccessible/stale source | `CHANGE_DATA_SOURCE`, `RETRIEVE_MORE`, `ABSTAIN` | Alternate authorized source | Alternate source + stronger verification | When source authority is ambiguous | `ABSTAIN` |
| `RETRIEVAL_FAILURE` | low coverage / weak retrieval | `RETRIEVE_MORE`, `RERANK`, `CHANGE_DATA_SOURCE`, `VERIFY` | Autonomous recovery | Recovery only with policy-permitted evidence standard | When evidence remains material/conflicting | `ABSTAIN` |
| `MODEL_FAILURE` | timeout, low capability, malformed output | `CHANGE_MODEL`, `REGENERATE`, `INCREASE_COMPUTE`, `VERIFY` | Switch/retry within budget | Switch + verify; avoid increasing autonomy | Sometimes | `ABORT` / `ABSTAIN` |
| `REASONING_FAILURE` | inconsistency / uncertainty | `INCREASE_COMPUTE`, `CHANGE_MODEL`, `VERIFY`, `REGENERATE` | Autonomous when bounded | Stronger model + verifier; human for high impact if unresolved | Often for high-impact unresolved cases | `ABSTAIN` |
| `EVIDENCE_FAILURE` | insufficient/contradictory/stale evidence | `RETRIEVE_MORE`, `RERANK`, `CHANGE_DATA_SOURCE`, `VERIFY` | Recover if evidence can be improved | Strong verification; do not force conclusion | If conflict affects high-impact decision | `ABSTAIN` |
| `POLICY_FAILURE` | policy denial / missing authorization | `REDACT`, `ASK_CLARIFICATION`, `HUMAN_REVIEW`, `BLOCK`, `ABORT` | Only explicitly allowed modifications | No autonomous bypass | Usually if exception is possible | `BLOCK` |
| `TOOL_FAILURE` | timeout/schema/error/unknown outcome | `REPAIR`, `RETRY`, `CHANGE_DATA_SOURCE`, `VERIFY` | Retry if safe/idempotent | Avoid blind retries; verify external state | If external side effect is uncertain/high-impact | `ABORT` / `HUMAN_REVIEW` |
| `RESOURCE_FAILURE` | budget/latency exhaustion | `DECREASE_COMPUTE`, `KEEP`, `ABSTAIN`, `ABORT` | Degrade safely | Preserve required verification and policy | When high-impact action cannot finish safely | `ABORT` / `ABSTAIN` |

### Cross-cutting failure classes

| Cross-cutting condition | Control implication |
|---|---|
| Provider failure | Treat as capability availability failure; use normalized provider abstraction |
| Evaluation failure | Never claim “verified”; recover evaluation or escalate |
| Privacy/security failure | Prefer `REDACT`, `BLOCK`, `ABORT`, or `HUMAN_REVIEW` |
| Agentic/action failure | Reassess authorization, side-effect state, and compensation capability |
| Multi-agent composition failure | Evaluate cumulative trajectory risk and lineage |
| Behavioral drift | Update observed profiles and future routing; preserve history |
| Observability failure | Pause/block/abort when safe governance cannot be established |
| Budget exhaustion | Stop bounded recovery and select a safe terminal/degraded state |

---

# Self-Healing Boundaries

The ControlPlane runtime must make the recovery boundary explicit in the plan or policy context.

```text
max_replans
max_model_calls
max_tool_calls
max_latency
max_cost
max_risk
max_retry_count
```

A recovery action is valid only if it fits inside the **remaining** boundary.

### Recovery budget rule

```text
remaining recovery budget
=
original allowance
-
consumed execution
-
reserved mandatory verification
```

### No unbounded self-healing

The following runtime pattern is prohibited:

```text
failure
 ↓
retry
 ↓
failure
 ↓
retry
 ↓
...
 ↓
success
```

The required pattern is:

```text
failure
 ↓
diagnose
 ↓
check eligibility
 ↓
select bounded intervention
 ↓
replan
 ↓
execute
 ↓
verify
 ↓
finish / degrade / escalate / abstain / block / abort
```

---

# Decision and Audit Requirements

Every material recovery decision should leave a structured trace sufficient to answer:

```text
What failed?
How was it detected?
How confident was the diagnosis?
What evidence supported the diagnosis?
Which policy applied?
What intervention was selected?
Why was that intervention eligible?
What budgets remained?
What changed in the execution plan?
Was an external side effect already present?
Was human approval required?
Did the intervention help?
What was the final outcome?
```

Structured rationale is required; private model chain-of-thought is not.

A material recovery action should link to:

```text
failure event
trajectory
decision
policy
plan version before
plan version after
intervention
verification
final outcome
```

---

# Prototype Scope vs Future Scope

| Capability | Competition Prototype / R2 | Future production scope |
|---|---|---|
| Failure taxonomy | Formal nine-class taxonomy with cross-cutting subtypes | Versioned taxonomy with domain-specific extensions |
| Failure detection | Structured events + baseline evaluators + runtime signals | Learned/anomaly-aware detection and adaptive thresholds |
| Diagnosis | Rule/policy-assisted structured diagnosis | Probabilistic root-cause inference over trajectories |
| Intervention selection | Policy + heuristic/score-based bounded selection | Learned intervention policy with counterfactual evaluation |
| Replanning | Event-triggered plan versioning | Rich dynamic workflow synthesis with stronger guarantees |
| Retry limits | Explicit configurable counters | Adaptive budgets learned from outcome distributions |
| Cost budget | Track actual and estimated cost | Predictive cost models and multi-objective optimization |
| Latency budget | Per-request budget accounting | Tail-latency aware adaptive control |
| Risk limits | Structured risk dimensions + policy thresholds | Calibrated trajectory-level risk models |
| Human escalation | Manual approval gate and decision record | Policy-driven human workflow, SLAs, routing, delegation |
| Abstention | Explicit terminal state | Calibrated uncertainty/abstention policies |
| Blocking | Runtime policy gate | Distributed policy enforcement with stronger guarantees |
| Graceful degradation | Defined safe fallback states | SLO-aware degradation orchestration |
| Partial execution | Explicit trajectory/ledger representation | External-state reconciliation and richer recovery orchestration |
| Rollback | Representation only; no false rollback guarantee | Integration with systems that provide real rollback primitives |
| Compensation | Conceptual contract | Verified compensating-action workflows |
| Failure isolation | Node/branch/provider-level isolation | Bulkheads, circuit breakers, quota domains, regional isolation |
| Provider failure | Normalized provider abstraction | Automated provider health scoring and failover |
| Retrieval failure | Retrieval/rerank/source fallback | Adaptive retrieval planning and learned source selection |
| Model failure | Model switch + bounded regeneration | Dynamic model portfolios and reliability-aware routing |
| Evaluation failure | Alternative verifier / human fallback | Evaluator ensembles with calibration and redundancy |
| Tool failure | Safe retry/repair with side-effect awareness | Idempotency-aware transactional orchestration |
| Policy failure | Block/redact/human | Versioned policy/rule packs with governance lifecycle |
| Data failure | Alternate source / abstention | Data quality contracts and freshness-aware source orchestration |
| Reasoning failure | Stronger model / more compute / verification | Learned compute allocation and reasoning verification policies |
| Evidence conflict | Additional retrieval / verification / abstention | Provenance-aware conflict resolution and source trust models |
| Privacy/security failure | Redact/block/abort | Enterprise-grade data-loss prevention and policy enforcement |
| Agentic/action failure | Human gate + post-action verification | Transactional action governance and compensation systems |
| Multi-agent failure | Shared trajectory + cumulative risk | Formal multi-agent policy and provenance controls |
| Behavioral drift | Telemetry and observed profiles | Online drift detection and adaptive model/capability profiles |
| Observability failure | Event/trace health checks | Redundant telemetry paths and governance-safe fail-closed modes |
| Budget exhaustion | Controlled degraded/terminal states | Predictive budget allocation across concurrent trajectories |
| Recovery telemetry | Structured intervention and outcome records | Longitudinal recovery analytics and learning loops |

## Prototype boundary

The prototype demonstrates the architectural control loop:

```text
failure
 → detection
 → diagnosis
 → bounded intervention
 → replan
 → execute
 → verify
 → final outcome
```

It does **not** claim universal recovery of arbitrary external systems, deterministic replay of the entire external world, automatic rollback of unsupported systems, or unrestricted autonomous remediation.

The architecture is intentionally designed so stronger production and research recovery mechanisms can replace the prototype heuristics without changing the fundamental ControlPlane contracts.

---

## Final Recovery Principle

> **A failure is a governance event, not merely an error. ControlPlane must understand what failed, determine whether recovery is safe and worthwhile, choose a bounded intervention, replan the trajectory, verify the resulting state, and then finish, degrade, escalate, abstain, block, or abort without hiding what happened.**
