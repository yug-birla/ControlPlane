# controlplane/db/

**Purpose:** the only place SQLAlchemy is configured and the only place ORM models are declared. Nothing else in the codebase should call `sqlalchemy.create_engine` or open a raw connection.

## Interface

- `engine.py`: `get_engine()`, `get_session_factory()`, `session_scope()` (a context manager  -  commits on success, rolls back on exception, always closes). Every write in `controlplane/trajectory/`, `controlplane/ledger/`, `controlplane/events/`, and `controlplane/runtime.py` goes through `session_scope()`.
- `models.py`: `RequestRecord`, `TrajectoryRecord`, `TrajectoryStepRecord`, `ExecutionLedgerRecord`, `EventRecord`, `ModelInvocationRecord`  -  implement `docs/DATA/POSTGRES_SCHEMA.md` §3.1, §9, §10.1, §8.1, §10.2. `new_id(prefix)` generates the project's identifier format (see `controlplane/context.py`).

## Dependencies

PostgreSQL, reached via `DATABASE_URL` (`controlplane/config.py`). Schema changes go through Alembic (`alembic/`), never applied by hand.

## Limitations

One session per store-method call (no cross-store transactions yet  -  e.g. creating a trajectory and appending its first ledger entry are two separate commits). Acceptable at current scale per `docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md`'s "no distributed transactions" guidance; revisit if a future layer needs atomicity across them.

## Extension points

Later layers add new ORM models here (e.g. `plans`/`plan_versions` for Layer 4-5, `evaluations` for Layer 13) rather than creating a second place models are declared.
