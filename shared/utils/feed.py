"""Agent Feed writer shared by every service that surfaces agent activity.

Each entry is persisted to ``agent_feed`` (history for the Feed screen) and
published on the ``logpilot:agent_feed`` Redis channel, which the API gateway
relays to connected consoles over the ``/ws`` WebSocket.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

FEED_CHANNEL = "logpilot:agent_feed"

FEED_ENTRY_TYPES = {
    "anomaly_detected",
    "risk_score_updated",
    "chat_answer",
    "ingestion_completed",
    "alert_fired",
    "report_drafted",
    "agent_observation",
}


async def record_feed_entry(
    db: AsyncSession,
    *,
    entry_type: str,
    title: str,
    body: str | None = None,
    service_name: str | None = None,
    severity: str | None = None,
    risk_score: float | None = None,
    source_session_id: str | None = None,
    source_chat_message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    organization_id: str | None = None,
) -> dict[str, Any]:
    """Insert a feed row and return it in the shape the console expects.

    The caller owns the transaction (commit after this returns).
    """
    if entry_type not in FEED_ENTRY_TYPES:
        entry_type = "agent_observation"
    result = await db.execute(
        text("""
            INSERT INTO agent_feed (
                entry_type, service_name, title, body,
                severity, risk_score,
                source_session_id, source_chat_message_id,
                metadata, organization_id
            ) VALUES (
                CAST(:entry_type AS feedentrytype), :service_name, :title, :body,
                :severity, :risk_score,
                CAST(:source_session_id AS uuid), CAST(:source_chat_message_id AS uuid),
                CAST(:metadata AS jsonb), CAST(:organization_id AS uuid)
            )
            RETURNING id, created_at, is_read
        """),
        {
            "entry_type": entry_type,
            "service_name": service_name,
            "title": title,
            "body": body,
            "severity": severity,
            "risk_score": risk_score,
            "source_session_id": source_session_id,
            "source_chat_message_id": source_chat_message_id,
            "metadata": json.dumps(metadata or {}),
            "organization_id": organization_id,
        },
    )
    row = result.one()
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "entry_type": entry_type,
        "service_name": service_name,
        "title": title,
        "body": body,
        "severity": severity,
        "risk_score": risk_score,
        "source_session_id": source_session_id,
        "source_chat_message_id": source_chat_message_id,
        "metadata": metadata or {},
        "is_read": row.is_read,
    }


def publish_feed_entry(redis_url: str, entry: dict[str, Any]) -> None:
    """Best-effort push of a persisted entry to live consoles."""
    try:
        import redis

        redis.from_url(redis_url).publish(FEED_CHANNEL, json.dumps(entry, default=str))
    except Exception as exc:  # the row is already persisted; live push is optional
        logger.warning("Failed to publish feed entry: %s", exc)
