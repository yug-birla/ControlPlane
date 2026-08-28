# controlplane/capabilities/

**Purpose:** real capability implementations that the `GraphExecutor` invokes for `SQL`/`RAG` nodes, replacing the `MOCKED` handler used through Milestone 3. See `docs/ALGORITHMS/SQL_CAPABILITY.md` and `docs/ALGORITHMS/RAG_PIPELINE.md`.

## Interface

- `sql_setup.py`: `build_database()` — one-time SQLite build from `data/synthetic_enterprise/nexaconsult_enterprise.sql` (idempotent, never run from a request path).
- `sql_capability.py`: `SQLCapability.execute(query_text, k=None) -> dict` — template-matched, read-only, parameterized entity filtering.
- `rag_capability.py`: `RAGCapability.execute(query_text, k=None) -> dict` — wraps `controlplane.rag.retrieval` + `.adequacy`.

## Dependencies

`controlplane.rag.*`, stdlib `sqlite3`.

## Limitations

SQL: 5 fixed templates, not general NL2SQL (deliberate, see algorithm doc). RAG: 30-document corpus only.

## Extension points

WEB/CHAT_HISTORY/MEMORY/AGENT capabilities would each add one module here plus one handler entry in `controlplane/runtime.py::_execute_graph`'s `handlers` dict — no other change needed.
