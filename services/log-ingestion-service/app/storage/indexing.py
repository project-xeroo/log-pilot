"""
Tool 04 — Structured Storage & Indexing Tool
==============================================
Handles bulk insertion of parsed + redacted log records into PostgreSQL.
Manages:
  - Batch inserts with COPY-style efficiency (INSERT with executemany)
  - Full-text search tsvector column maintenance (via PostgreSQL trigger)
  - Date-partitioned queries (index on timestamp)
  - Vector index scaffolding (pgvector extension, embedding column)

The actual vector index creation and embedding population happen in the
processing-worker's embedding task (Phase 2 scope). This module creates
the scaffolding DDL and provides the storage interface.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from shared.models import (
    LogRecord,
    LogSession,
    IngestionStatus,
    LogFormat,
    SeverityLevel,
    AgentAction,
    AutonomyTier,
)

log = structlog.get_logger()

# Batch size for bulk inserts — tuned for ~10,000 records/minute target
_BATCH_SIZE = 500


def _map_severity(raw: str) -> str:
    """Map raw severity string to a valid SeverityLevel enum value."""
    mapping = {
        "TRACE": "TRACE", "DEBUG": "DEBUG", "INFO": "INFO",
        "WARN": "WARN", "WARNING": "WARNING", "ERROR": "ERROR",
        "CRITICAL": "CRITICAL", "FATAL": "FATAL",
    }
    return mapping.get((raw or "").upper(), "UNKNOWN")


def _map_format(raw: str) -> str:
    """Map raw format string to LogFormat enum value."""
    mapping = {
        "apache_common": "apache_common",
        "apache_combined": "apache_combined",
        "nginx": "nginx",
        "json": "json",
        "syslog": "syslog",
        "custom": "custom",
    }
    return mapping.get(raw, "unknown")


async def bulk_insert_records(
    db: AsyncSession,
    session_id: uuid.UUID,
    parsed_records: list[dict[str, Any]],
) -> int:
    """
    Insert a list of parsed record dicts into log_records in batches.
    Returns the count of successfully inserted records.
    """
    if not parsed_records:
        return 0

    inserted = 0
    for batch_start in range(0, len(parsed_records), _BATCH_SIZE):
        batch = parsed_records[batch_start : batch_start + _BATCH_SIZE]
        rows = []
        for r in batch:
            rows.append({
                "session_id": session_id,
                "timestamp": r.get("timestamp"),
                "service_name": r.get("service_name"),
                "severity": _map_severity(r.get("severity", "UNKNOWN")),
                "message": r.get("message"),
                "request_id": r.get("request_id"),
                "trace_id": r.get("trace_id"),
                "environment": r.get("environment"),
                "deployment_version": r.get("deployment_version"),
                "source_ip": r.get("source_ip"),
                "http_method": r.get("http_method"),
                "http_path": r.get("http_path"),
                "http_status": r.get("http_status"),
                "duration_ms": r.get("duration_ms"),
                "log_format": _map_format(r.get("log_format", "unknown")),
                "raw_line": r.get("raw_line") if not r.get("pii_was_redacted") else None,
                "extra_fields": r.get("extra_fields") or {},
                "pii_was_redacted": r.get("pii_was_redacted", False),
                "is_malformed": r.get("is_malformed", False),
            })

        stmt = pg_insert(LogRecord).values(rows)
        await db.execute(stmt)
        inserted += len(rows)

    return inserted


async def update_session_status(
    db: AsyncSession,
    session_id: uuid.UUID,
    status: str,
    detected_format: str | None = None,
    total_lines: int | None = None,
    parsed_records: int | None = None,
    failed_records: int | None = None,
    pii_redacted_count: int | None = None,
    error_message: str | None = None,
) -> None:
    """Update processing statistics on the log_sessions row."""
    from sqlalchemy import select, update

    values: dict[str, Any] = {"status": status}
    if detected_format is not None:
        values["detected_format"] = _map_format(detected_format)
    if total_lines is not None:
        values["total_lines"] = total_lines
    if parsed_records is not None:
        values["parsed_records"] = parsed_records
    if failed_records is not None:
        values["failed_records"] = failed_records
    if pii_redacted_count is not None:
        values["pii_redacted_count"] = pii_redacted_count
    if error_message is not None:
        values["error_message"] = error_message

    stmt = (
        update(LogSession)
        .where(LogSession.id == session_id)
        .values(**values)
    )
    await db.execute(stmt)


async def ensure_full_text_search_trigger(db: AsyncSession) -> None:
    """
    Create the PostgreSQL tsvector trigger for full-text search on message field.
    Idempotent — safe to call on every startup.
    """
    await db.execute(text("""
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
    """))
    await db.execute(text("""
        ALTER TABLE log_records
        ADD COLUMN IF NOT EXISTS message_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(message, ''))) STORED;
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_log_records_message_tsv
        ON log_records USING gin(message_tsv);
    """))
    log.info("storage.fts_trigger.ensured")


async def ensure_vector_index_scaffolding(db: AsyncSession) -> None:
    """
    Scaffold pgvector extension and embedding column on log_records.
    The actual embeddings are generated by the processing-worker in Phase 2.
    Idempotent — safe to call on every startup.
    """
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    await db.execute(text("""
        ALTER TABLE log_records
        ADD COLUMN IF NOT EXISTS embedding vector(1536);
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_log_records_embedding_ivfflat
        ON log_records USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """))
    log.info("storage.vector_index.scaffolded")


async def write_audit_action(
    db: AsyncSession,
    tool_name: str,
    trigger: str,
    session_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str = "completed",
    error: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> None:
    """Write an entry to the agent_actions audit table."""
    action = AgentAction(
        tool_name=tool_name,
        trigger=trigger,
        autonomy_tier=AutonomyTier.AUTONOMOUS.value,
        actor_user_id=actor_user_id,
        session_id=session_id,
        input_summary=input_summary,
        output_summary=output_summary,
        status=status,
        error=error,
        organization_id=organization_id,
    )
    db.add(action)
    await db.flush()
