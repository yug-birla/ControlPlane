"""One-time setup: builds ``data/synthetic_enterprise/nexaconsult.db``
(SQLite) from ``data/synthetic_enterprise/nexaconsult_enterprise.sql``.

Why SQLite, not the main ControlPlane Postgres instance: the seed script
is written in SQLite syntax (``PRAGMA journal_mode``, ``julianday('now')``
in its views) -- it was authored for SQLite, not Postgres, and
``docs/DATA/POSTGRES_SCHEMA.md``'s ``enterprise_demo`` Postgres schema
(``init_postgres_schema.sql``) defines tables but ships no seed data at
all (verified: zero ``INSERT``/``COPY`` statements in that file). Rather
than rewrite 580+ lines of SQLite-specific SQL and fabricate seed data
for the Postgres version, this uses the real, existing, data-complete
SQLite script as-is. This is demo/reference data for one capability
(SQL), entirely separate from ControlPlane's own operational state
(trajectories/ledger/events/etc.), which remains exclusively in
Postgres per docs/PROJECT_STATE/DECISIONS.md's "one relational system"
decision -- see docs/PROJECT_STATE/DECISIONS.md for this milestone's
entry recording the choice.

Never run from a request path -- setup only, like
``controlplane.models.model_download``.

Run:
    .venv/Scripts/python -m controlplane.capabilities.sql_setup
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SEED_SQL_PATH = Path(__file__).resolve().parents[2] / "data/synthetic_enterprise/nexaconsult_enterprise.sql"
DB_PATH = Path(__file__).resolve().parents[2] / "data/synthetic_enterprise/nexaconsult.db"


def build_database(force: bool = False) -> Path:
    if DB_PATH.exists() and not force:
        return DB_PATH

    if DB_PATH.exists():
        DB_PATH.unlink()

    sql_script = _SEED_SQL_PATH.read_text(encoding="utf-8-sig")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(sql_script)
        conn.commit()
    finally:
        conn.close()
    return DB_PATH


if __name__ == "__main__":
    path = build_database(force=True)
    conn = sqlite3.connect(path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    views = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()]
    conn.close()
    print(f"Built {path} ({path.stat().st_size} bytes): {len(tables)} tables, {len(views)} views")
    print("Tables:", tables)
    print("Views:", views)
