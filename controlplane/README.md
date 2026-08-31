# controlplane/ (Milestone 7  -  Real Agent/Tool Governance, Behavioral Drift, Permission Lineage, Prompt-Injection Detection, Hard Judge Benchmark)

**Purpose:** the full request lifecycle  -  Query Profiler → Risk Profiler → Policy → Capability/Model Router → Execution Graph (real SQL + RAG-with-reranking + **real, governed Agent/Tool execution**) → Evaluation (10 real per-request evaluators + a standalone Bias comparator + a real-but-offline LLM Judge) → Decision (now including Agent-Governance and Prompt-Injection hard constraints) → Intervention → Replan → re-Evaluate → Verify → Trust → response. Behavioral Drift and Permission Lineage exist as real, standalone/derived capabilities; still no Shadow Mode.

## Interface

- `POST /v1/requests {"query": str, "application_id": str | null}` → `ResponseEnvelope`. `metadata` includes `trust` (the derived `TrustAssessment`), and `evaluation` now includes `agent_governance`/`prompt_injection` results when applicable.
- `GET /health/live`, `GET /health/ready`.
- `GET /dashboard`, `GET /dashboard/requests/{id}`, `GET /dashboard/api/*`  -  read-only observability, now including a Trust panel and a Permission Lineage / Agent Governance panel (`controlplane/dashboard/`).
- `controlplane.runtime.Runtime.handle(ctx, state) -> state`  -  orchestrates the full lifecycle; `_run_control_loop` implements Decide → (Intervene → Replan → re-Evaluate)* → Verify, bounded to `max_attempts=2` (one retry); Trust is computed once the loop terminates.
- `controlplane/{execution,routing,query_intelligence,risk,policy,capabilities,rag,evaluation,decision,intervention,verification,trust,governance,judge,dashboard,experiments,models,trajectory,ledger,events,db}/`  -  see each subfolder's own `README.md`.

## Dependencies

Milestone 4/5/6's stack, unchanged  -  no new third-party dependency this milestone. `AgentCapability` reuses the existing `SQLCapability` and writes real files only to the sandboxed `data/agent_reports/` directory.

## Limitations (intentional, Milestone 7 scope)

- `max_attempts=2`  -  one bounded retry, not unlimited self-healing (unchanged from Milestone 5).
- `AgentCapability`'s tool vocabulary is 3 real tools + 1 hard-blocked stub, not the full canonical action space  -  a small, fixed, deterministic set is what makes the governance gate meaningful (an LLM proposing arbitrary tool calls would defeat the point).
- `send_notification`'s actual send is `MOCKED` (no real external notification channel configured for this prototype).
- Behavioral Drift (`controlplane/governance/behavioral_drift.py`) is real but demonstrated only on a SYNTHETIC baseline history  -  not wired into any live decision path, since no real historical AGENT-action volume exists yet to validate against.
- Permission Lineage is single-hop (one tool call per request)  -  no multi-agent composition tracking (bootstrap SS27, not attempted).
- LLM-Judge subsystem (`controlplane/judge/`) remains real but NOT in the live per-request Evaluation Suite  -  measured Local Judge latency is 30-90s/call on this CPU-only machine.
- No independent verifier model  -  Verification reads the same evaluator signals the Decision Engine already read.
- FAST/STRONG Model Router roles both resolve to Groq; Gemini remains a separate, conservatively-used comparison-only provider (not live-validated this session  -  no API key present).
- WEB/CHAT_HISTORY/MEMORY capabilities still run via the `MOCKED` handler (AGENT is real as of this milestone).
- Shadow Mode (Layer 20) remains not started.

## Extension points

- A learned Decision/Intervention policy would implement the same interfaces as `controlplane.decision.engine.DecisionEngine`/`controlplane.intervention.engine.InterventionEngine`.
- New `AgentCapability` tools slot into its deterministic keyword-pattern dispatch without changing `AgentGate`'s interface.
- `controlplane.governance.behavioral_drift.BehavioralDriftDetector` is ready to wire into the live Decision Engine once real historical AGENT-action volume exists to baseline against.
- A faster/smaller local judge (quantized, or a different model) would only need to implement the same `.evaluate(task, *, query, answer, evidence) -> JudgeResult` contract as `controlplane.judge.LocalJudge`.
- Multi-provider Model Routing (Layer 10's remaining scope) extends `controlplane.models.registry.get_configured_provider` without changing `controlplane.routing.model_router`.
