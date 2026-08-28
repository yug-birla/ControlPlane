# controlplane/ (Milestone 6 — Cross-Encoder Reranker, LLM Judge, Reasoning/Bias Evaluators, Agent Governance, Trust Layer)

**Purpose:** the full request lifecycle — Query Profiler → Risk Profiler → Policy → Capability/Model Router → Execution Graph (real SQL + RAG, RAG now including a real cross-encoder reranking stage) → Evaluation (8 real per-request evaluators + a standalone Bias comparator + a real-but-offline LLM Judge) → Decision (now including CONFLICTING-evidence handling) → Intervention → Replan → re-Evaluate → Verify → **Trust** → response. Still no live agent/tool execution, no Behavioral Drift, no Shadow Mode.

## Interface

- `POST /v1/requests {"query": str, "application_id": str | null}` → `ResponseEnvelope`. `metadata` now additionally includes `trust` (the derived `TrustAssessment`).
- `GET /health/live`, `GET /health/ready`.
- `GET /dashboard`, `GET /dashboard/requests/{id}`, `GET /dashboard/api/*` — read-only observability, now including a Trust panel (`controlplane/dashboard/`).
- `controlplane.runtime.Runtime.handle(ctx, state) -> state` — orchestrates the full lifecycle; `_run_control_loop` implements Decide → (Intervene → Replan → re-Evaluate)* → Verify, bounded to `max_attempts=2` (one retry); Trust is computed once the loop terminates.
- `controlplane/{execution,routing,query_intelligence,risk,policy,capabilities,rag,evaluation,decision,intervention,verification,trust,governance,judge,dashboard,experiments,models,trajectory,ledger,events,db}/` — see each subfolder's own `README.md`.

## Dependencies

Milestone 4/5's stack, unchanged — `cross-encoder/ms-marco-MiniLM-L-6-v2` and `Qwen/Qwen2.5-1.5B-Instruct` are both loaded through the already-present `sentence-transformers`/`transformers`/`torch` dependencies, no new package added.

## Limitations (intentional, Milestone 6 scope)

- `max_attempts=2` — one bounded retry, not unlimited self-healing (unchanged from Milestone 5).
- LLM-Judge subsystem (`controlplane/judge/`) is real but NOT in the live per-request Evaluation Suite — measured Local Judge latency is 30-90s/call on this CPU-only machine, vs. the rest of the suite's sub-100ms total.
- Agent Governance gate (`controlplane/governance/agent_gate.py`) is real and measured against real trajectory data, but not wired into any live execution path — the `AGENT` capability itself is still `MOCKED`.
- Bias evaluator (`controlplane/evaluation/bias.py`) is real but standalone/comparative, not part of the per-request `EvaluationSuite`.
- No independent verifier model — Verification reads the same evaluator signals the Decision Engine already read.
- FAST/STRONG Model Router roles both resolve to Groq; Gemini remains a separate, conservatively-used comparison-only provider (not live-validated this session — no API key present).
- WEB/CHAT_HISTORY/MEMORY/AGENT capabilities still run via the `MOCKED` handler.
- Behavioral Drift, Permission Lineage, Partial Execution states, and Shadow Mode (Layers 19-20) remain not started.

## Extension points

- A learned Decision/Intervention policy would implement the same interfaces as `controlplane.decision.engine.DecisionEngine`/`controlplane.intervention.engine.InterventionEngine`.
- Once a real `AGENT` capability exists, its execution handler would call `controlplane.governance.agent_gate.AgentGate.evaluate_step` before each tool invocation.
- A faster/smaller local judge (quantized, or a different model) would only need to implement the same `.evaluate(task, *, query, answer, evidence) -> JudgeResult` contract as `controlplane.judge.LocalJudge`.
- Multi-provider Model Routing (Layer 10's remaining scope) extends `controlplane.models.registry.get_configured_provider` without changing `controlplane.routing.model_router`.
