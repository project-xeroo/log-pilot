"""
Ingestion proxy router — forwards log upload/status requests to the ingestion service.
Protected by JWT + RBAC.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, status

from app.auth import get_current_user, require_role, TokenPayload
from app.config import settings

log = structlog.get_logger()
router = APIRouter(prefix="/ingest", tags=["ingestion"])

# All ingestion endpoints require at minimum developer role
_dev_or_above = require_role("developer")


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a log file [Tool 01]",
)
async def proxy_upload(
    request: Request,
    file: UploadFile = File(...),
    service_name: str | None = Form(None),
    environment: str | None = Form(None),
    user: Annotated[TokenPayload, Depends(_dev_or_above)] = None,
):
    """
    RBAC-protected proxy: forwards file upload to the log-ingestion-service.
    Requires developer role or above.
    """
    content = await file.read()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.ingestion_service_url}/ingest/upload",
            files={"file": (file.filename, content, file.content_type or "application/octet-stream")},
            data={
                k: v for k, v in {
                    "service_name": service_name,
                    "environment": environment,
                }.items() if v is not None
            },
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post(
    "/api",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest log records via API [Tool 01]",
)
async def proxy_api_ingest(
    payload: dict,
    user: Annotated[TokenPayload, Depends(_dev_or_above)] = None,
):
    """Proxy API-based log ingestion to the ingestion service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ingestion_service_url}/ingest/api",
            json=payload,
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get(
    "/status/{session_id}",
    summary="Get ingestion session status [Tool 01]",
)
async def proxy_status(
    session_id: uuid.UUID,
    user: Annotated[TokenPayload, Depends(get_current_user)] = None,
):
    """Return ingestion status for a session (all authenticated users)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.ingestion_service_url}/ingest/status/{session_id}",
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
