<<<<<<< HEAD
from .db import get_session, engine, init_db
from .pagination import PaginatedResponse, paginate

__all__ = ["get_session", "engine", "init_db", "PaginatedResponse", "paginate"]
=======
"""Shared async SQLAlchemy engine / session factory."""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import DatabaseSettings

_settings = DatabaseSettings()

engine = create_async_engine(
    _settings.url,
    pool_size=_settings.pool_size,
    max_overflow=_settings.max_overflow,
    pool_timeout=_settings.pool_timeout,
    echo=_settings.echo,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
