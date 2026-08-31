# controlplane/events/

**Purpose:** the canonical event contract (`docs/architecture/EVENT_MODEL.md`)  -  "what happened," never "what should happen" (that's `controlplane/runtime.py`, the only place that interprets an event and decides).

## Interface

- `schema.py`: `EventType` (currently `QUERY_RECEIVED`, `MODEL_CALLED`, `MODEL_FAILURE`, `FINAL_RESPONSE_GENERATED`  -  a subset of EVENT_MODEL.md's ~29-event taxonomy), `Severity` (transport-level: `info/notice/warning/high/critical`), `Event.create(...)`.
- `transport.py`: `EventTransport` (ABC) + `InProcessEventTransport` (synchronous pub/sub). Replaceable  -  a Redis Streams-backed transport can implement the same interface later without touching any publisher or subscriber.
- `store.py`: `EventStore.persist(event)` / `get_by_trajectory(...)`  -  one of the transport's subscribers, responsible for durable history (`event_index` table).

## Dependencies

`controlplane/db/` (via `EventStore`). No message broker yet.

## Limitations

In-process only  -  events don't survive a process crash between publish and a subscriber's persist call (no at-least-once delivery guarantee yet). Fine for the current single-process prototype; revisit before any multi-worker deployment.

## Extension points

New event types get added to `EventType` only when something actually emits them  -  don't pre-declare events nothing produces (see `docs/architecture/EVENT_MODEL.md` §14 for the full canonical list to draw from later).
