"""
Chat proxy router — forwards chat requests to the AI service.
Protected by JWT (any authenticated user can chat).
"""
from __future__ import annotations

from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import TokenPayload, permission_checker
from shared.models import Permission
from app.config import settings

log = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])

_authenticated = permission_checker(Permission.chat_use)


@router.post(
    "",
    summary="Ask a question about your logs [proxy → ai-service]",
)
async def proxy_chat(
    payload: dict,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ai_service_url}/chat",
            json=payload,
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post(
    "/stream",
    summary="Ask a question — streaming response [proxy → ai-service]",
)
async def proxy_chat_stream(
    payload: dict,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    """Proxy streaming SSE response from the AI service."""
    async def event_generator():
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{settings.ai_service_url}/chat/stream",
                json=payload,
            ) as resp:
                async for chunk in resp.aiter_text():
                    yield chunk

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post(
    "/rate",
    summary="Rate a chat message [proxy → ai-service]",
    status_code=204,
)
async def proxy_rate(
    payload: dict,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{settings.ai_service_url}/chat/rate",
            json=payload,
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)


@router.get(
    "/sessions",
    summary="List chat sessions [proxy → ai-service]",
)
async def proxy_list_sessions(
    request: Request,
    user: Annotated[TokenPayload, Depends(_authenticated)] = None,
):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{settings.ai_service_url}/chat/sessions",
            params=dict(request.query_params),
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
