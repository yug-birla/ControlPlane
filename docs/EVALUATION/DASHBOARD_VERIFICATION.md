# Dashboard Verification

**Date:** 2026-08-29. **Verified against a running server**, not by reading templates.

## How to run it

```bash
# Postgres must be up first (docker start controlplane_postgres)
setx HF_HOME "E:\ControlPlane\.cache\huggingface"          # once, per README
.venv/Scripts/python -m uvicorn controlplane.main:app --host 127.0.0.1 --port 8000
```

| URL | What it shows |
|---|---|
| `http://127.0.0.1:8000/dashboard` | Request list |
| `http://127.0.0.1:8000/dashboard/requests/{id}` | Full execution trace for one request |
| `http://127.0.0.1:8000/dashboard/health-map` | System-wide component health |
| `http://127.0.0.1:8000/dashboard/api/component-health` | Same, as JSON |

No API key is required: with none configured the runtime falls back to the local Qwen provider, so the whole system runs offline.

## Verification checklist

Every item below was checked by fetching the live URL and asserting on the returned HTML.

| # | Item | Result |
|---|---|---|
| 1 | Backend starts | OK |
| 2 | Frontend served (Jinja templates, same process) | OK |
| 3 | Dashboard opens | OK — opened in the default browser |
| 4 | Create a request (`POST /v1/requests`) | OK — real request, Qwen3-4B |
| 5 | Request appears in the dashboard | OK |
| 6 | Execution graph appears | OK — 5 nodes with real statuses |
| 7 | Logs / trajectory appear | OK |
| 8 | Events appear | OK |
| 9 | Plan evolution appears | OK — verified on a request that actually replanned |
| 10 | Model routing appears | OK |
| 11 | MCP appears | OK — *added during this verification* |
| 12 | Agent communication appears | OK — HANDOFF edges with sensitivity |
| 13 | State appears | OK |
| 14 | Evaluation appears | OK |
| 15 | Failure localization appears | OK — *added during this verification* |

Items 11 and 15 were **missing on first check**. The data existed in the detail payload but no template rendered it, so they were built rather than documented as gaps — which is what §72 asks for.

Plan evolution renders only when a request actually replanned. That is correct behaviour, not a gap: the panel is absent when there is no second plan, rather than showing an empty section implying one existed.

## What the verification actually caught

**Starting the server and reading one answer exposed a critical regression that all 409 tests had missed.**

The request *"Look up Q4 revenue in the database and the travel policy document, then send a notification to finance"* ran a 3-agent plan with two gatherers in parallel. Every node reported `COMPLETED`. The answer was:

> "I don't have direct access to external databases or documents..."

`grounding` reported `NOT_APPLICABLE` with rationale *"no RAG node ran"* — while `agent_retriever` had completed RAG in 1391ms. Evidence collectors still keyed on `node.capability == "RAG"`, but a gatherer agent's capability is `"AGENT"` with the real capability in `input_ref["serves_capability"]`.

The request was nonetheless **VERIFIED with trust HIGH**, because grounding was `NOT_APPLICABLE` rather than `UNSUPPORTED`. *Evidence never arriving* and *evidence not being required* were indistinguishable to the evaluators.

Notably, **failure localization had already diagnosed it correctly** —

> `attribution: COMPONENT_FAILURE`, `component: CAPABILITY_ROUTER` — *"no retrieval node ran; the model was never given evidence to ground against, so this is a routing failure"*

— but that panel was not rendered, so nobody could see it. The component that would have reported the bug was built and silent. Both the bug and the missing panel are fixed.

**After the fix**, on a live request:

| | Before | After |
|---|---|---|
| Answer | "I don't have direct access…" | "…meal reimbursement limit for domestic travel is up to **$75 per day**" |
| `grounding` | `NOT_APPLICABLE` | **`SUPPORTED`** (0.58 term overlap with retrieved evidence) |
| `rag_adequacy` | `NOT_APPLICABLE` | **`SUFFICIENT`** |
| Trust | HIGH (unearned) | HIGH (earned) |

## Performance

The map and diagnostics panels are derived from the detail payload already fetched, adding **no queries**. `aggregate_component_health` uses three queries regardless of how many requests are scanned — deliberately, because a Milestone 5 N+1 regression once made a routine test run take 101 seconds.

## Limitations

- Rendering is server-side Jinja with inline SVG and vanilla JS. No CDN, no build step, works offline — but also no live streaming; the page reflects state at load.
- The execution map lays nodes out by dependency depth. A very wide graph will scroll horizontally rather than re-flow.
- The component-health view scans the 200 most recent requests, not all history.
