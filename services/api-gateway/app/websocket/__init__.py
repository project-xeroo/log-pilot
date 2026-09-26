"""
WebSocket connection manager and Redis event relay.

The gateway exposes a single WebSocket (``/ws``, see ``router.py``). Backend
services never talk to browsers directly: they publish on Redis channels and
this module relays each message to the connected consoles as a typed event.

Channel → event type → permission required to receive it:
  logpilot:agent_feed    → feed_event   (feed:read)   Agent Feed entries
  logpilot:ws_broadcast  → alert_event  (alert:read)  pre-incident alerts
                                                       (via notification-service)
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

import redis.asyncio as aioredis
import structlog
from fastapi import WebSocket

from app.config import settings
from shared.models import Permission, has_permission

log = structlog.get_logger()


@dataclass(frozen=True)
class _Route:
    event_type: str
    permission: Permission


CHANNEL_ROUTES: dict[str, _Route] = {
    "logpilot:agent_feed": _Route("feed_event", Permission.feed_read),
    "logpilot:ws_broadcast": _Route("alert_event", Permission.alert_read),
}


class ConnectionManager:
    """Registry of active WebSocket connections, keyed by user."""

    def __init__(self) -> None:
        # user_id (str) → set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._roles: dict[str, str] = {}

    async def connect(self, websocket: WebSocket, user_id: str, role: str) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)
        self._roles[user_id] = role
        log.info("ws.connected", user_id=user_id, total=self._total())

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            del self._connections[user_id]
            self._roles.pop(user_id, None)
        log.info("ws.disconnected", user_id=user_id, total=self._total())

    async def send_to_user(self, user_id: str, message: dict) -> None:
        """Send a JSON message to all connections for a specific user."""
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self._connections[user_id].discard(ws)

    async def broadcast(self, message: dict, permission: Permission | None = None) -> None:
        """Send a JSON message to every connected user holding ``permission``."""
        for user_id in list(self._connections):
            if permission and not has_permission(self._roles.get(user_id, ""), permission):
                continue
            await self.send_to_user(user_id, message)

    def _total(self) -> int:
        return sum(len(v) for v in self._connections.values())


# Singleton — used by the WebSocket endpoint and the Redis relay
manager = ConnectionManager()


async def redis_event_relay() -> None:
    """
    Background task (started in the gateway lifespan): subscribe to every
    channel in CHANNEL_ROUTES and fan messages out as typed WebSocket events.
    """
    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(*CHANNEL_ROUTES)
    log.info("ws.relay.subscribed", channels=list(CHANNEL_ROUTES))

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()
            route = CHANNEL_ROUTES.get(channel)
            if route is None:
                continue
            try:
                data = json.loads(message["data"])
            except (TypeError, ValueError):
                log.warning("ws.relay.bad_payload", channel=channel)
                continue
            await manager.broadcast({"type": route.event_type, "data": data}, route.permission)
    finally:
        await pubsub.aclose()
        await r.aclose()
