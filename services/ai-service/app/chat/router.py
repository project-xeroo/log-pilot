"""
Chat router — conversational Q&A with source citations + rating endpoints.

POST /chat            — ask a question, get a sourced answer (non-streaming)
POST /chat/stream     — streaming variant (tokens via Server-Sent Events)
POST /chat/rate       — submit a thumbs up/down rating for a message
GET  /chat/sessions   — list chat sessions for the authenticated user
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.engine import execute_chat, stream_chat
from app.chat.schemas import ChatRatingRequest, ChatRequest, ChatResponse

log = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# DB dependency — overridden by main.py
# ---------------------------------------------------------------------------

async def _get_db() -> AsyncSession:  # type: ignore[return]
    raise NotImplementedError


# ---------------------------------------------------------------------------
# POST /chat — non-streaming
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ChatResponse,
    summary="Ask a question about your logs [Tool Chat]",
    description=(
        "Accepts a plain-language question. Retrieves the most relevant log records "
        "via semantic similarity search, then calls the reasoning model to produce "
        "a sourced, evidence-backed answer with record citations."
    ),
)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(_get_db),
) -> ChatResponse:
    return await execute_chat(request, db)


# ---------------------------------------------------------------------------
# POST /chat/stream — streaming (Server-Sent Events)
# ---------------------------------------------------------------------------

@router.post(
    "/stream",
    summary="Ask a question — streaming response (SSE)",
    description=(
        "Same as POST /chat but streams tokens as Server-Sent Events. "
        "The first event contains __meta__:<session_id>:<message_id>. "
        "Subsequent events are token chunks."
    ),
)
async def chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(_get_db),
):
    async def event_generator() -> AsyncIterator[str]:
        async for token in stream_chat(request, db):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# POST /chat/rate — helpfulness rating (PRD: target > 80% helpful)
# ---------------------------------------------------------------------------

@router.post(
    "/rate",
    summary="Rate a chat message",
    description="Submit a thumbs-up or thumbs-down rating for a chat response.",
    status_code=204,
)
async def rate_message(
    rating: ChatRatingRequest,
    db: AsyncSession = Depends(_get_db),
) -> None:
    await db.execute(
        text("""
            INSERT INTO chat_ratings (message_id, helpful, comment, created_at)
            VALUES (CAST(:message_id AS uuid), :helpful, :comment, now())
            ON CONFLICT (message_id) DO UPDATE
                SET helpful = EXCLUDED.helpful,
                    comment = EXCLUDED.comment,
                    updated_at = now()
        """),
        {
            "message_id": rating.message_id,
            "helpful": rating.helpful,
            "comment": rating.comment,
        },
    )
    log.info("chat.rated", message_id=rating.message_id, helpful=rating.helpful)


# ---------------------------------------------------------------------------
# GET /chat/sessions — list sessions for the current user
# ---------------------------------------------------------------------------

@router.get(
    "/sessions",
    summary="List chat sessions",
)
async def list_sessions(
    db: AsyncSession = Depends(_get_db),
    limit: int = 20,
    offset: int = 0,
) -> dict:
    result = await db.execute(
        text("""
            SELECT id, user_id, created_at, updated_at
            FROM chat_sessions
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    )
    sessions = [dict(r._mapping) for r in result]
    return {"sessions": sessions, "limit": limit, "offset": offset}
