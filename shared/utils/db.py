from __future__ import annotations

from functools import lru_cache
from typing import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker, Session

from shared.config import get_settings
from shared.models import Base


def _sync_url(url: str) -> str:
    """DATABASE_URL is configured for asyncpg; this sync engine needs psycopg2."""
    for prefix in ("postgresql+asyncpg://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


@lru_cache
def get_engine() -> Engine:
    """Created on first use so importing shared.utils does not require psycopg2."""
    return create_engine(_sync_url(get_settings().database_url), pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables (dev / testing helper — prefer Alembic in production)."""
    Base.metadata.create_all(bind=get_engine())


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
