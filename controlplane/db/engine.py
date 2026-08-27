"""SQLAlchemy engine/session -- the only module that opens a DB connection.

PostgreSQL is the documented prototype datastore
(docs/PROJECT_STATE/DECISIONS.md; docs/DATA/DATA_STORAGE_ARCHITECTURE.md).
This module preserves that decision; nothing else in the codebase should
import ``sqlalchemy.create_engine`` directly.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from controlplane.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
