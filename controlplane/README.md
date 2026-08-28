# controlplane/ (Milestone 5 — Decision, Intervention, Replanning, Verification)

**Purpose:** the full request lifecycle — Query Profiler → Risk Profiler → Policy → Capability/Model Router → Execution Graph (real SQL + RAG capabilities) → Evaluation → **Decision → Intervention → Replan → re-Evaluate → Verify** → response. Still no learned/semantic routing improvements, no Reasoning/Bias evaluators, no Agent/Tool governance.

## Interface

- `POST /v1/requests {"query": str, "application_id": str | null}` → `ResponseEnvelope`. `metadata` now includes `capability_route`, `model_route`, `evaluation` (list of evaluator results, including `NOT_IMPLEMENTED` ones), `decision` (the terminal `ControlDecision`), `verification` (the final `VerificationResult`).
- `GET /health/live`, `GET /health/ready`.
- `GET /dashboard`, `GET /dashboard/requests/{id}`, `GET /dashboard/api/*` — read-only observability, including the full Decision/Intervention/Replan/Verification trail per request (`controlplane/dashboard/`).
- `controlplane.runtime.Runtime.handle(ctx, state) -> state` — orchestrates the full lifecycle; `_run_control_loop` implements Decide → (Intervene → Replan → re-Evaluate)* → Verify, bounded to `max_attempts=2` (one retry).
- `controlplane/{execution,routing,query_intelligence,risk,policy,capabilities,rag,evaluation,decision,intervention,verification,dashboard,experiments,models,trajectory,ledger,events,db}/` — see each subfolder's own `README.md`.

## Dependencies

Milestone 4's stack (`google-genai`, `jinja2` added) — no other new third-party dependency this milestone.

## Limitations (intentional, Milestone 5 scope)

- `max_attempts=2` — one bounded retry, not unlimited self-healing.
- Reasoning/Bias evaluators remain `NOT_IMPLEMENTED` (see `docs/ALGORITHMS/EVALUATION_LAYER.md` for why).
- No independent verifier model — Verification reads the same evaluator signals the Decision Engine already read.
- FAST/STRONG Model Router roles both resolve to Groq; Gemini remains a separate, conservatively-used comparison-only provider.
- WEB/CHAT_HISTORY/MEMORY/AGENT capabilities still run via the `MOCKED` handler (SQL and RAG are real as of Milestone 4/5).
- A real, critical fix landed this milestone: through Milestone 4, the model's prompt never actually included retrieved SQL/RAG evidence — see `docs/PROJECT_STATE/DECISIONS.md` and `docs/EVALUATION/RAG_RESULTS.md`.

## Extension points

- A learned Decision/Intervention policy would implement the same interfaces as `controlplane.decision.engine.DecisionEngine`/`controlplane.intervention.engine.InterventionEngine`.
- A cross-encoder reranker slots into `controlplane.rag.retrieval` without changing its callers.
- Multi-provider Model Routing (Layer 10's remaining scope) extends `controlplane.models.registry.get_configured_provider` without changing `controlplane.routing.model_router`.
