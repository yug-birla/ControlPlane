# controlplane/dashboard/

**Purpose:** read-only observability surface over real Postgres data  -  request list, per-request detail (query → profile → risk → route → graph → decision/intervention/replan → verification → answer → evaluation), and aggregate stats.

## Interface

- `queries.py`: `list_recent_requests()`, `get_request_detail(request_id)`, `aggregate_stats()`  -  pure SELECTs, batched (no N+1  -  see the fix noted in `docs/PROJECT_STATE/PROGRESS.md`).
- `router.py`: `GET /dashboard` (HTML), `GET /dashboard/requests/{id}` (HTML, the "WHY" panel), `GET /dashboard/api/requests[/{id}]`, `GET /dashboard/api/stats` (JSON).
- `templates/`: Jinja2 (auto-escaping  -  query text and answers are rendered safely).

## Dependencies

`fastapi.templating.Jinja2Templates`. No JS framework, no build step (bootstrap: "grow the product, not infrastructure").

## Limitations

Manual-refresh, not live/streaming (stated explicitly in the page header)  -  a real, current read on every load, not a fake live feed.

## Extension points

A future live-updating view would add a WebSocket/SSE endpoint alongside the existing JSON API without changing `queries.py`.
