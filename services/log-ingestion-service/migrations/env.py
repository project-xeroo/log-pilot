"""Alembic environment — the single migration chain for the shared LogPilot database.

All services share one Postgres schema, so every table (ingestion, forecasting,
analysis, chat/feed, reporting) is migrated from here.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Make `shared` (repo root) and `app` (this service) importable regardless of cwd
_here = os.path.dirname(os.path.abspath(__file__))
_service_root = os.path.dirname(_here)
_repo_root = os.path.dirname(os.path.dirname(_service_root))
for _p in (_repo_root, _service_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.config import settings  # noqa: E402
import shared.models  # noqa: E402,F401 — registers every model on Base.metadata
from shared.models import Base  # noqa: E402

# Alembic config
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """DATABASE_URL may be given with either the sync or asyncpg driver."""
    url = os.environ.get("DATABASE_URL", settings.database_url)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations():
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online())


run_migrations()
