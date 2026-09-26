"""
Search proxy router — forwards search requests to the AI service.
Protected by JWT + RBAC (any authenticated user can search).
"""
from __future__ import annotations

from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import TokenPayload, permission_checker
from shared.models import Permission
from app.config import settings

log = structlog.get_logger()
router = APIRouter(prefix="/search", tags=["search"])

# Any authenticated user can search
_authenticated = permission_checker(Permission.search_read)


@router.post(
    "",
    summary="Search log records [proxy → ai-service]",
)
async def proxy_search_post(
    payload: dict,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    """Proxy POST /search to the AI service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.ai_service_url}/search",
            json=payload,
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get(
    "",
    summary="Search log records (GET) [proxy → ai-service]",
)
async def proxy_search_get(
    request: Request,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    """Proxy GET /search (with all query params) to the AI service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.ai_service_url}/search",
            params=dict(request.query_params),
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get(
    "/filters",
    summary="Get available filter values [proxy → ai-service]",
)
async def proxy_search_filters(
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    """Proxy GET /search/filters to the AI service."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{settings.ai_service_url}/search/filters")
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
