"""
Processing Pipeline Task — parse → redact → store
==================================================
This is the core Phase 1 processing task.

Pipeline:
  1. Download raw file from object storage
  2. Tool 02: Parse all lines → ParsedRecord list
  3. Tool 03: Redact PII from every field of every record  [MANDATORY]
  4. Tool 04: Bulk-insert into PostgreSQL + update session status
  5. Audit-log the action to agent_actions

Throughput target: > 10,000 records/minute
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from typing import Any

import boto3
import structlog
from botocore.config import Config
from celery import Task
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.main import celery_app
from app.config import settings

log = structlog.get_logger()

# Sync SQLAlchemy engine for Celery tasks
_engine = create_engine(
    settings.database_url_sync,
    pool_size=5,
    max_overflow=10,
)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def _get_s3_client():
    kwargs: dict[str, Any] = {
        "region_name": settings.storage_region,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if settings.storage_endpoint_url:
        kwargs["endpoint_url"] = settings.storage_endpoint_url
    if settings.storage_access_key_id:
        kwargs["aws_access_key_id"] = settings.storage_access_key_id
        kwargs["aws_secret_access_key"] = settings.storage_secret_access_key
    return boto3.client("s3", **kwargs)


def _download_from_storage(storage_key: str) -> bytes:
    """Download raw file content from object storage."""
    s3 = _get_s3_client()
    response = s3.get_object(Bucket=settings.storage_bucket, Key=storage_key)
    return response["Body"].read()


@celery_app.task(
    name="app.tasks.ingestion.process_log_session",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    queue="ingestion",
)
def process_log_session(self: Task, session_id: str, storage_key: str) -> dict:
    """
    Main processing pipeline task.
    Called by the ingestion service immediately after upload.
    """
    # Inline imports (parsers and redaction live in the ingestion service package)
    # The processing worker mounts the ingestion service as a sibling package via
    # the Docker PYTHONPATH or a local pip install. Both services share this code.
    from log_ingestion_service.app.parsers import parse_content  # type: ignore[import]
    from log_ingestion_service.app.redaction import redact, redact_record_fields  # type: ignore[import]

    sid = uuid.UUID(session_id)

    log.info("pipeline.start", session_id=session_id, storage_key=storage_key)

    with _SessionLocal() as db:
        _update_session_status(db, sid, "processing")

        try:
            # Step 1 — Download
            content = _download_from_storage(storage_key)
            filename = storage_key.split("/")[-1]

            # Step 2 — Parse (Tool 02)
            parsed_records, dominant_format = parse_content(content, filename)
            total = len(parsed_records)
            log.info("pipeline.parsed", session_id=session_id, total=total, format=dominant_format)

            # Step 3 — PII Redaction (Tool 03) — MANDATORY, runs on every record
            rows = []
            pii_total = 0
            failed = 0

            for record in parsed_records:
                if record.is_malformed and not record.message:
                    failed += 1
                    rows.append(_record_to_row(record, sid, pii_redacted=False))
                    continue

                pii_count = 0
                if record.message:
                    r = redact(record.message)
                    record.message = r.text
                    pii_count += r.replacements
                if record.raw_line and pii_count == 0:
                    # Only keep raw_line if no PII was found in the message
                    r2 = redact(record.raw_line)
                    if r2.replacements > 0:
                        record.raw_line = None  # Drop PII-contaminated raw line
                        pii_count += r2.replacements
                if record.extra_fields:
                    redacted_extras, extra_pii = redact_record_fields(record.extra_fields)
                    record.extra_fields = redacted_extras
                    pii_count += extra_pii

                pii_total += pii_count
                rows.append(_record_to_row(record, sid, pii_redacted=(pii_count > 0)))

            # Step 4 — Bulk insert (Tool 04)
            inserted = _bulk_insert(db, rows)
            log.info("pipeline.stored", session_id=session_id, inserted=inserted)

            # Update session
            _update_session_status(
                db, sid,
                status="completed",
                detected_format=dominant_format,
                total_lines=total,
                parsed_records=inserted,
                failed_records=failed,
                pii_redacted_count=pii_total,
            )

            # Step 5 — Audit log
            _write_audit(
                db,
                tool_name="log_ingestion_pipeline",
                trigger="upload",
                session_id=sid,
                input_summary=f"file={filename}, lines={total}",
                output_summary=f"inserted={inserted}, pii_redacted={pii_total}, failed={failed}",
            )

            db.commit()

            # Step 6 — Phase 2: enqueue embedding generation (fire-and-forget)
            # Runs after commit so records are visible to the embedding task.
            _enqueue_embeddings(session_id)

            return {
                "session_id": session_id,
                "status": "completed",
                "total_lines": total,
                "inserted": inserted,
                "pii_redacted": pii_total,
                "failed": failed,
            }

        except Exception as exc:
            db.rollback()
            log.error("pipeline.failed", session_id=session_id, error=str(exc), exc_info=True)
            _update_session_status(db, sid, "failed", error_message=str(exc))
            _write_audit(
                db,
                tool_name="log_ingestion_pipeline",
                trigger="upload",
                session_id=sid,
                status="failed",
                error=str(exc),
            )
            db.commit()
            raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Helpers (sync)
# ---------------------------------------------------------------------------

def _record_to_row(record, session_id: uuid.UUID, pii_redacted: bool) -> dict:
    return {
        "session_id": str(session_id),
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "service_name": record.service_name,
        "severity": record.severity or "UNKNOWN",
        "message": record.message,
        "request_id": record.request_id,
        "trace_id": record.trace_id,
        "environment": record.environment,
        "deployment_version": record.deployment_version,
        "source_ip": record.source_ip,
        "http_method": record.http_method,
        "http_path": record.http_path,
        "http_status": record.http_status,
        "duration_ms": record.duration_ms,
        "log_format": record.log_format or "unknown",
        "raw_line": record.raw_line if not pii_redacted else None,
        "extra_fields": json.dumps(record.extra_fields or {}, default=str),
        "pii_was_redacted": pii_redacted,
        "is_malformed": record.is_malformed,
    }


_BATCH_SIZE = 500


def _bulk_insert(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    inserted = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        db.execute(
            text("""
                INSERT INTO log_records (
                    session_id, timestamp, service_name, severity, message,
                    request_id, trace_id, environment, deployment_version,
                    source_ip, http_method, http_path, http_status, duration_ms,
                    log_format, raw_line, extra_fields, pii_was_redacted, is_malformed
                ) VALUES (
                    :session_id, :timestamp, :service_name, CAST(:severity AS severitylevel), :message,
                    :request_id, :trace_id, :environment, :deployment_version,
                    :source_ip, :http_method, :http_path, :http_status, :duration_ms,
                    CAST(:log_format AS logformat), :raw_line, CAST(:extra_fields AS jsonb), :pii_was_redacted, :is_malformed
                )
            """),
            batch,
        )
        inserted += len(batch)
    return inserted


def _update_session_status(
    db: Session,
    session_id: uuid.UUID,
    status: str,
    detected_format: str | None = None,
    total_lines: int | None = None,
    parsed_records: int | None = None,
    failed_records: int | None = None,
    pii_redacted_count: int | None = None,
    error_message: str | None = None,
) -> None:
    sets = ["status = :status"]
    params: dict[str, Any] = {"status": status, "session_id": str(session_id)}
    if detected_format is not None:
        sets.append("detected_format = CAST(:detected_format AS logformat)")
        params["detected_format"] = detected_format
    if total_lines is not None:
        sets.append("total_lines = :total_lines")
        params["total_lines"] = total_lines
    if parsed_records is not None:
        sets.append("parsed_records = :parsed_records")
        params["parsed_records"] = parsed_records
    if failed_records is not None:
        sets.append("failed_records = :failed_records")
        params["failed_records"] = failed_records
    if pii_redacted_count is not None:
        sets.append("pii_redacted_count = :pii_redacted_count")
        params["pii_redacted_count"] = pii_redacted_count
    if error_message is not None:
        sets.append("error_message = :error_message")
        params["error_message"] = error_message
    db.execute(
        text(f"UPDATE log_sessions SET {', '.join(sets)} WHERE id = CAST(:session_id AS uuid)"),
        params,
    )


def _write_audit(
    db: Session,
    tool_name: str,
    trigger: str,
    session_id: uuid.UUID | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str = "completed",
    error: str | None = None,
) -> None:
    db.execute(
        text("""
            INSERT INTO agent_actions (
                tool_name, trigger, autonomy_tier, session_id,
                input_summary, output_summary, status, error
            ) VALUES (
                :tool_name, :trigger, 'autonomous',
                CAST(:session_id AS uuid),
                :input_summary, :output_summary, :status, :error
            )
        """),
        {
            "tool_name": tool_name,
            "trigger": trigger,
            "session_id": str(session_id) if session_id else None,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "status": status,
            "error": error,
        },
    )


def _enqueue_embeddings(session_id: str) -> None:
    """
    Enqueue the Phase 2 embedding generation task for a completed session.
    Fire-and-forget: ingestion pipeline is not affected if this fails.
    """
    try:
        from app.embeddings import generate_embeddings_for_session
        generate_embeddings_for_session.apply_async(
            args=[session_id],
            countdown=2,   # brief delay so the commit is fully visible
            queue="embeddings",
        )
        log.info("embeddings.enqueued", session_id=session_id)
    except Exception as exc:
        # Never let embedding scheduling break the ingestion result
        log.warning("embeddings.enqueue_failed", session_id=session_id, error=str(exc))
