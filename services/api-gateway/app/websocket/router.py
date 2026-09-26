"""
WebSocket endpoint — /ws  (the console's single real-time channel)

Clients connect with a JWT token as a query parameter:
    wss://host/ws?token=<jwt>

Server → client events (see ``app.websocket.CHANNEL_ROUTES``):
  {"type": "feed_event",  "data": <FeedEntry>}   new Agent Feed entry
  {"type": "alert_event", "data": {...}}         pre-incident alert fired
  {"type": "ping"}                               keepalive every 30 seconds
"""
from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from app.auth import decode_access_token
from app.websocket import manager

log = structlog.get_logger()
router = APIRouter(tags=["websocket"])

_PING_INTERVAL_SECONDS = 30


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """
    Real-time stream of agent activity for the console.

    Protocol:
      Client → Server:  {"type": "ping"}
      Server → Client:  {"type": "pong"}
      Server → Client:  {"type": "feed_event" | "alert_event", "data": {...}}
    """
    # Authenticate
    try:
        payload = decode_access_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return
    user_id = payload.sub

    await manager.connect(websocket, user_id, payload.role)
    ping_task = asyncio.create_task(_ping_loop(websocket))

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # Client silent for 60s — send ping to check liveness
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws.error", user_id=user_id, error=str(exc))
    finally:
        ping_task.cancel()
        manager.disconnect(websocket, user_id)


async def _ping_loop(websocket: WebSocket) -> None:
    """Send a server-initiated ping every _PING_INTERVAL_SECONDS."""
    while True:
        await asyncio.sleep(_PING_INTERVAL_SECONDS)
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"type": "ping"})
        except Exception:
            break
