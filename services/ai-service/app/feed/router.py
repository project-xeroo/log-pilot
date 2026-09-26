"""
Agent Feed router — chronological stream of what the agent has noticed/said/drafted.

GET  /feed           — paginated list of feed entries
POST /feed           — internal: create a new feed entry (called by agent services)
POST /feed/{id}/read — mark a feed entry as read
GET  /feed/unread    — count of unread entries
"""
from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from shared.utils.feed import publish_feed_entry, record_feed_entry

log = structlog.get_logger()
router = APIRouter(prefix="/feed", tags=["feed"])


# ---------------------------------------------------------------------------
# DB dependency — overridden by main.py
# ---------------------------------------------------------------------------

async def _get_db() -> AsyncSession:  # type: ignore[return]
    raise NotImplementedError


# ---------------------------------------------------------------------------
# GET /feed — paginated feed entries (newest first)
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="Get agent feed entries",
    description=(
        "Returns the chronological stream of what the agent has noticed, said, or drafted. "
        "This is the data source for the Agent Feed (home) screen."
    ),
)
async def get_feed(
    db: AsyncSession = Depends(_get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    entry_type: str | None = Query(None),
    service_name: str | None = Query(None),
    unread_only: bool = Query(False),
) -> dict:
    where = []
    params: dict = {"limit": limit, "offset": offset}

    if entry_type:
        where.append("entry_type::text = :entry_type")
        params["entry_type"] = entry_type
    if service_name:
        where.append("service_name = :service_name")
        params["service_name"] = service_name
    if unread_only:
        where.append("is_read = false")

    where_clause = "WHERE " + " AND ".join(where) if where else ""

    result = await db.execute(
        text(f"""
            SELECT
                id, created_at, entry_type, service_name,
                title, body, severity, risk_score,
                source_session_id, source_chat_message_id,
                metadata, is_read
            FROM agent_feed
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    entries = [dict(r._mapping) for r in result]

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM agent_feed {where_clause}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_result.scalar_one()

    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# GET /feed/unread — unread count badge
# ---------------------------------------------------------------------------

@router.get("/unread", summary="Count unread feed entries")
async def get_unread_count(db: AsyncSession = Depends(_get_db)) -> dict:
    result = await db.execute(
        text("SELECT COUNT(*) FROM agent_feed WHERE is_read = false")
    )
    return {"unread": result.scalar_one()}


# ---------------------------------------------------------------------------
# POST /feed — create a feed entry (called internally by agent services)
# ---------------------------------------------------------------------------

@router.post(
    "",
    summary="Create a feed entry [internal]",
    status_code=201,
)
async def create_feed_entry(
    payload: dict,
    db: AsyncSession = Depends(_get_db),
) -> dict:
    """
    Internal endpoint — called by other services (processing worker, forecasting)
    to push events into the agent feed. Not exposed through the gateway to end users.
    The entry is persisted and relayed live to consoles via the gateway WebSocket.
    """
    entry = await record_feed_entry(
        db,
        entry_type=payload.get("entry_type", "agent_observation"),
        title=payload.get("title", ""),
        body=payload.get("body"),
        service_name=payload.get("service_name"),
        severity=payload.get("severity"),
        risk_score=payload.get("risk_score"),
        source_session_id=payload.get("source_session_id"),
        source_chat_message_id=payload.get("source_chat_message_id"),
        metadata=payload.get("metadata"),
        organization_id=payload.get("organization_id"),
    )
    await db.commit()
    publish_feed_entry(settings.redis_url, entry)
    return {"id": entry["id"], "created_at": entry["created_at"]}


# ---------------------------------------------------------------------------
# POST /feed/{id}/read — mark entry as read
# ---------------------------------------------------------------------------

@router.post("/{entry_id}/read", summary="Mark feed entry as read", status_code=204)
async def mark_read(
    entry_id: int,
    db: AsyncSession = Depends(_get_db),
) -> None:
    await db.execute(
        text("UPDATE agent_feed SET is_read = true WHERE id = :id"),
        {"id": entry_id},
    )
