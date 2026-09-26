"""
Log Ingestion Service — FastAPI application entry point.
Exposes Tool 01: file upload, API ingestion, and streaming endpoints.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.validators import validate_upload
from app.storage import upload_bytes

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# DB engine (local to this service — can share with shared/ later)
# ---------------------------------------------------------------------------
_engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)
_SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("log_ingestion_service.startup", service=settings.service_name)
    yield
    await _engine.dispose()
    log.info("log_ingestion_service.shutdown")


app = FastAPI(
    title="LogPilot — Log Ingestion Service",
    description="Tool 01: Multi-format log ingestion (upload, API, streaming)",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "service": settings.service_name}


# ---------------------------------------------------------------------------
# Tool 01 — Log Ingestion Router
# ---------------------------------------------------------------------------

@app.post(
    "/ingest/upload",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingestion"],
    summary="Upload a log file (Tool 01)",
    description=(
        "Accepts .log, .txt, .json, .csv, .zip, or .gz files up to 500 MB. "
        "The file is stored in object storage and a processing task is enqueued immediately. "
        "Returns the session_id to track processing status."
    ),
)
async def upload_log_file(
    file: UploadFile = File(..., description="Log file to ingest"),
    service_name: str | None = Form(None, description="Service name tag for this upload"),
    environment: str | None = Form(None, description="Environment tag (e.g. production)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Tool 01 — File Upload Endpoint.
    Validates, stores, and enqueues the uploaded log file for parsing.
    """
    from shared.models import LogSession, IngestionStatus

    validate_upload(file)

    session_id = uuid.uuid4()
    filename = file.filename or f"upload-{session_id}.log"

    # Read the full file content (validated <= 500 MB above)
    content = await file.read()
    actual_size = len(content)

    if actual_size > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File content is {actual_size} bytes — exceeds 500 MB limit.",
        )

    # Store raw file in object storage
    storage_key = await upload_bytes(
        session_id=session_id,
        filename=filename,
        data=content,
        content_type=file.content_type or "application/octet-stream",
    )

    # Create session record
    log_session = LogSession(
        id=session_id,
        filename=filename,
        file_size_bytes=actual_size,
        source_type="upload",
        content_type=file.content_type,
        storage_key=storage_key,
        status=IngestionStatus.PENDING,
    )
    db.add(log_session)
    await db.flush()

    # Enqueue processing task (Celery)
    _enqueue_processing(str(session_id), storage_key)

    log.info(
        "ingestion.upload.accepted",
        session_id=str(session_id),
        filename=filename,
        size_bytes=actual_size,
    )

    return {
        "session_id": str(session_id),
        "filename": filename,
        "size_bytes": actual_size,
        "status": "pending",
        "message": "File accepted. Processing will begin within 5 seconds.",
    }


@app.post(
    "/ingest/api",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingestion"],
    summary="Ingest log records via JSON API (Tool 01)",
    description="Push an array of raw log line strings for immediate parsing and storage.",
)
async def ingest_api(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Tool 01 — API Ingestion Endpoint.
    Accepts: {"service": "...", "lines": ["raw log line", ...]}
    """
    from shared.models import LogSession, IngestionStatus
    import json

    lines: list[str] = payload.get("lines", [])
    service: str | None = payload.get("service")

    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'lines' array is required and must not be empty.",
        )
    if len(lines) > 100_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Maximum 100,000 lines per API ingestion call.",
        )

    session_id = uuid.uuid4()
    # Serialise lines to JSON and store as a pseudo-file
    content = json.dumps({"service": service, "lines": lines}).encode()
    filename = f"api-{session_id}.json"

    storage_key = await upload_bytes(
        session_id=session_id,
        filename=filename,
        data=content,
        content_type="application/json",
    )

    log_session = LogSession(
        id=session_id,
        filename=filename,
        file_size_bytes=len(content),
        source_type="api",
        content_type="application/json",
        storage_key=storage_key,
        status=IngestionStatus.PENDING,
    )
    db.add(log_session)
    await db.flush()

    _enqueue_processing(str(session_id), storage_key)

    log.info("ingestion.api.accepted", session_id=str(session_id), line_count=len(lines))

    return {
        "session_id": str(session_id),
        "line_count": len(lines),
        "status": "pending",
    }


@app.get(
    "/ingest/status/{session_id}",
    tags=["ingestion"],
    summary="Get ingestion session status (Tool 01)",
)
async def get_session_status(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return processing status and statistics for an ingestion session."""
    from shared.models import LogSession
    from sqlalchemy import select

    result = await db.execute(select(LogSession).where(LogSession.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return {
        "session_id": str(session.id),
        "filename": session.filename,
        "status": session.status,
        "detected_format": session.detected_format,
        "total_lines": session.total_lines,
        "parsed_records": session.parsed_records,
        "failed_records": session.failed_records,
        "pii_redacted_count": session.pii_redacted_count,
        "error_message": session.error_message,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enqueue_processing(session_id: str, storage_key: str) -> None:
    """
    Enqueue a Celery task to process the uploaded file.
    Import is deferred to avoid Celery worker dependency at import time.
    """
    try:
        from app.tasks import process_log_session
        process_log_session.apply_async(
            args=[session_id, storage_key],
            countdown=0,
            queue="ingestion",
        )
    except ImportError:
        # Processing worker not co-located — task is picked up by the worker service
        log.warning("celery_not_available_locally", session_id=session_id)
