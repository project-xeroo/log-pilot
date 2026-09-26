"""
WebSocket alert broadcaster.

The api-gateway maintains a registry of connected WebSocket clients.
A background task subscribes to the "logpilot:ws_broadcast" Redis
channel (where the notification-service publishes) and fans out every
message to all connected sockets.

Usage: mounted as /ws/alerts in main.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Set

import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect

from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_BROADCAST_CHANNEL = "logpilot:ws_broadcast"


class ConnectionManager:
    """Thread-safe registry of active WebSocket connections."""

    def __init__(self):
        self._active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)
        logger.debug("WS client connected; total=%d", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        logger.debug("WS client disconnected; total=%d", len(self._active))

    async def broadcast(self, message: str) -> None:
        """Send a text message to all connected clients, silently dropping dead connections."""
        dead: Set[WebSocket] = set()
        for ws in list(self._active):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._active -= dead


manager = ConnectionManager()


async def ws_endpoint(websocket: WebSocket) -> None:
    """FastAPI WebSocket route handler — mounts at /ws/alerts."""
    await manager.connect(websocket)
    try:
        # Keep connection alive; client can send pings, we ignore them
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def redis_broadcast_listener() -> None:
    """
    Background coroutine: subscribe to the Redis broadcast channel and
    fan out every message to all connected WebSocket clients.
    Started on application startup in main.py.
    """
    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(_BROADCAST_CHANNEL)
    logger.info("WS broadcaster subscribed to '%s'", _BROADCAST_CHANNEL)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            await manager.broadcast(message["data"])
        except Exception as exc:
            logger.error("WS broadcast error: %s", exc)
