"""
Phase 2 — Embedding Generation Task
=====================================
Celery task that takes a completed ingestion session, retrieves all
log_records that have no embedding yet, batches them through the cloud
embedding API, and writes the resulting vectors back to the DB.

Pipeline position: called by process_log_session() after successful ingestion.

Design constraints:
  - PII redaction is ALWAYS complete before this task runs (guaranteed by
    the ingestion pipeline ordering).
  - Batches records in groups of settings.embedding_batch_size (default 256)
    to stay within API rate limits and token limits.
  - On failure, only the failed batch is retried (partial progress is kept).
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from celery import Task
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.main import celery_app
from app.config import settings

log = structlog.get_logger()

# Sync engine (Celery tasks are sync; we use run_sync wrappers for async calls)
_engine = create_engine(
    settings.database_url_sync,
    pool_size=5,
    max_overflow=10,
)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Retry policy for embedding API calls
# ---------------------------------------------------------------------------

_RETRYABLE = (RateLimitError, APITimeoutError, APIError)


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(settings.provider_max_retries),
    wait=wait_exponential(
        multiplier=settings.provider_retry_wait_seconds,
        min=settings.provider_retry_wait_seconds,
        max=10.0,
    ),
    reraise=True,
)
async def _embed_batch(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Call the embedding API for one batch of texts."""
    # Truncate individual texts conservatively to avoid token limit errors
    texts = [t[:2000] if t else "" for t in texts]
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.embeddings.generate_embeddings_for_session",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    queue="embeddings",
)
def generate_embeddings_for_session(self: Task, session_id: str) -> dict:
    """
    Generate and store embeddings for all log_records in an ingestion session
    that do not yet have an embedding.

    Called automatically by the ingestion pipeline after a successful
    process_log_session() run.
    """
    import asyncio

    if not settings.openai_api_key:
        log.warning(
            "embeddings.skipped.no_api_key",
            session_id=session_id,
        )
        return {"session_id": session_id, "status": "skipped", "reason": "no_api_key"}

    sid = uuid.UUID(session_id)

    log.info("embeddings.start", session_id=session_id)

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.provider_timeout_seconds,
        max_retries=0,  # handled by tenacity above
    )

    try:
        result = asyncio.run(_embed_session(client, sid))
        log.info(
            "embeddings.done",
            session_id=session_id,
            embedded=result["embedded"],
            batches=result["batches"],
        )
        return {"session_id": session_id, "status": "completed", **result}
    except Exception as exc:
        log.error("embeddings.failed", session_id=session_id, error=str(exc), exc_info=True)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Async implementation (called via asyncio.run from the sync Celery task)
# ---------------------------------------------------------------------------

async def _embed_session(client: AsyncOpenAI, session_id: uuid.UUID) -> dict:
    """
    Fetch un-embedded records for the session, generate embeddings in batches,
    and write them back. Returns stats dict.
    """
    import asyncpg
    from app.config import settings as cfg

    # Use asyncpg directly for the vector update — SQLAlchemy sync driver
    # doesn't support the pgvector wire format natively.
    conn: asyncpg.Connection = await asyncpg.connect(
        cfg.database_url.replace("postgresql+asyncpg://", "postgresql://")
    )

    try:
        # Fetch IDs + messages for records with no embedding yet
        rows = await conn.fetch(
            """
            SELECT id, message
            FROM log_records
            WHERE session_id = $1
              AND embedding IS NULL
              AND is_malformed = false
            ORDER BY id
            """,
            session_id,
        )

        if not rows:
            return {"embedded": 0, "batches": 0}

        total_embedded = 0
        batch_count = 0
        batch_size = cfg.embedding_batch_size

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            ids = [r["id"] for r in batch]
            texts = [r["message"] or "" for r in batch]

            vectors = await _embed_batch(client, texts)

            # Write each vector back — pgvector expects '[f1,f2,...]' string format
            # or a native array; asyncpg with pgvector extension accepts list[float]
            updates = [
                (vector, record_id)
                for vector, record_id in zip(vectors, ids)
            ]
            await conn.executemany(
                "UPDATE log_records SET embedding = $1 WHERE id = $2",
                # pgvector asyncpg codec expects the list as-is when the
                # extension's type codec is registered
                [(f"[{','.join(str(v) for v in vec)}]", rid) for vec, rid in updates],
            )

            total_embedded += len(batch)
            batch_count += 1

            log.debug(
                "embeddings.batch_done",
                session_id=str(session_id),
                batch=batch_count,
                batch_size=len(batch),
                cumulative=total_embedded,
            )

        return {"embedded": total_embedded, "batches": batch_count}

    finally:
        await conn.close()
