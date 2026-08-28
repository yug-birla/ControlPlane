# ControlPlane.ai — Current State

**Last updated:** 2026-08-28 (Milestone 7)
**Context:** Accenture Innovation Challenge 2026, Round 2 — Prototype Development (Problem Track 1, "ControlPlane.ai"). See `Problem_Statement/` for the original brief (partially captured as screenshots; not yet transcribed to text — see `BLOCKERS.md`).

## What Exists

**Documentation:**
- `docs/ALGORITHMS/` — 15 prior files plus 1 new: `BEHAVIORAL_DRIFT.md`. `AGENT_GOVERNANCE.md`, `EVALUATION_LAYER.md`, `CONTROL_LOOP.md` updated for the real Agent/Tool wiring, Prompt-Injection evaluator, and the new hard-constraint decision branches.
- `docs/EVALUATION/` — 1 new: `BEHAVIORAL_DRIFT_RESULTS.md`. `EVALUATOR_RESULTS.md` (Judge HARD benchmark, Reasoning audit, Safety results), `AGENT_GOVERNANCE_RESULTS.md`, `CONTROL_LOOP_RESULTS.md`, `README.md` updated.
- `docs/PROJECT_STATE/` — this folder, updated; `BLOCKERS.md` gained B10 (low disk space causing environment-wide slowdowns, not a code defect).

**Application code (Milestone 7 — Real Agent/Tool Governance, Behavioral Drift, Permission Lineage, Prompt-Injection Detection, Hard Judge Benchmark — complete 2026-08-28):**

- **`controlplane/capabilities/agent_capability.py` (NEW):** the `AGENT` capability's real handler — 3 real tools (`sql_read_query`, `write_report`, `send_notification`) plus a hard-blocked `destructive_operation`, each gated live by `AgentGate` before running. Replaces the `MOCKED` handler used through Milestone 6.
- **`controlplane/governance/behavioral_drift.py` (NEW):** a real, tested frequency-based drift detector — standalone, demonstrated on a synthetic baseline (no real historical volume exists yet to validate against live).
- **`controlplane/dashboard/` extended:** a Permission Lineage panel, derived from the `AGENT` node's own trajectory step (same "derive, don't duplicate" pattern as Trust).
- **`controlplane/evaluation/evaluators.py` extended:** `AgentGovernancePassthroughEvaluator`, `PromptInjectionEvaluator` — both wired into the live default `EvaluationSuite` and into new Decision Engine hard-constraint branches.
- **Three real architectural bugs found and fixed making Agent Governance actually reachable, not assumed away:** (1) Policy blanket-restricted `AGENT` at `HIGH_RISK`, and the Risk Profiler always assigns agentic queries at least `HIGH_RISK` — so the capability was structurally unreachable; fixed by moving the hard restriction to `CRITICAL_ACTION` only. (2) "drop the customers table" never reached the AGENT capability because `"drop"` wasn't a recognized action keyword; fixed with a proximity-aware regex (`drop` near a data-object noun) plus new safe keywords (`truncate`/`wipe`/`purge`). (3) Trust reported HIGH for a response whose HIGH_RISK tool proposal was actually withheld pending human review, because Decision/Verification/Trust never consumed the AGENT node's own governance outcome; fixed with the new `agent_governance` evaluator + Decision Engine branch.
- **A genuinely harder LLM Judge benchmark built and run:** 24 hand-authored cases targeting paraphrase, hallucination, subtle numeric errors, and conflicting evidence — Milestone 6's 20-case benchmark was too easy (deterministic reached 1.0 accuracy). Real result: deterministic 0.292 accuracy, Local Judge 0.375 — a real, if partial, improvement concentrated in paraphrase-recognition and subtle-number categories, with a striking honest finding that the Local Judge never once predicted the middle `PARTIALLY_SUPPORTED` label across all 24 cases (0.0 precision/recall/F1 for that class) — it behaves as an effectively binary classifier at this model size.
- **Reasoning and Safety capability audits, both reported honestly including unflattering results:** `ReasoningEvaluator`'s in-scope recall measured at only 0.5 (missed a same-subject contradiction due to exact-phrase matching); `PromptInjectionEvaluator` measured at 1.0 accuracy including two deliberately-hard near-miss negative cases.
- `tests/` — 252 automated tests (up from 222), all passing.
- **A real environmental finding, not a code bug:** wall-clock test-suite time ballooned to 76+ minutes during this milestone (individual test durations remained sub-second) — traced to only ~4.5GB free disk space (likely from this milestone's ~3GB Local Judge model download), not a code regression. Documented as `BLOCKERS.md` B10, not "fixed" (freeing disk space is a user/environment decision).
- **Explicitly not implemented / deferred:** Shadow Mode (Layer 20); Behavioral Drift live-wiring (no real historical volume yet); multi-agent composition tracking; Bias dataset expansion beyond 8 pairs; fine-tuning of anything (the Judge's PARTIALLY_SUPPORTED gap is a real candidate, but few-shot prompting wasn't tried first).

**What does NOT exist:**
- No root-level `AGENTS.md` (`BLOCKERS.md` B1) — unchanged.
- No single `docs/ARCHITECTURE.md` file (`BLOCKERS.md` B2) — unchanged.
- Redis and Qdrant remain unused placeholders.
- No Shadow Mode (Layer 20).
- No live Groq-vs-Gemini benchmark at scale, and no live Gemini/Groq validation at all this session (no API keys present).
- No multi-step agent tool-calling loop (one `AGENT` node per graph) — Behavioral Drift and Permission Lineage are correspondingly single-hop.

## Phase

**Milestone 7 (Real Agent/Tool Governance + Behavioral Drift + Permission Lineage + Prompt-Injection Detection + Hard Judge Benchmark) complete.** Sequence: documentation audit (`4ae6a76`) → Layer 0 (`ac2f243`) → Layer 1 (`008231e`) → Milestone 1 (`463979e`) → Milestone 2 (`d396acb`) → Milestone 3 (`ba4896e`) → Milestones 4+5 (`7dc76a9`) → Milestone 6 (`a543f8c`) → Milestone 7 (pending commit). Awaiting explicit instruction before continuing — see `FUTURE_WORK.md`.
