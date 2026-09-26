"""
Feed proxy router — forwards feed requests to the AI service.
Protected by JWT (any authenticated user can view the feed).
"""
from __future__ import annotations

from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import TokenPayload, permission_checker
from shared.models import Permission
from app.config import settings

log = structlog.get_logger()
router = APIRouter(prefix="/feed", tags=["feed"])

_authenticated = permission_checker(Permission.feed_read)


@router.get("", summary="Get agent feed [proxy → ai-service]")
async def proxy_get_feed(
    request: Request,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.ai_service_url}/feed",
            params=dict(request.query_params),
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/unread", summary="Count unread feed entries [proxy → ai-service]")
async def proxy_unread(
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{settings.ai_service_url}/feed/unread")
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/{entry_id}/read", summary="Mark feed entry as read [proxy → ai-service]", status_code=204)
async def proxy_mark_read(
    entry_id: int,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(f"{settings.ai_service_url}/feed/{entry_id}/read")
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
