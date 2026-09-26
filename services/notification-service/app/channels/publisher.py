"""
Alert publisher — Redis pub/sub subscriber + WebSocket + webhook dispatch.

Subscribes to the "logpilot:alerts" Redis channel.
For every message received, it:
  1. Broadcasts to all connected WebSocket clients (real-time console push)
  2. Delivers to any configured webhook endpoints (HTTP POST)

WebSocket connections are managed by the api-gateway; this service
pushes to them via a shared Redis pub/sub channel the gateway subscribes to.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import redis.asyncio as aioredis

from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_ALERT_CHANNEL = "logpilot:alerts"
_WS_BROADCAST_CHANNEL = "logpilot:ws_broadcast"   # the api-gateway listens here


async def subscribe_and_dispatch(webhook_urls: list[str] | None = None) -> None:
    """
    Long-running coroutine: listens on the alerts Redis channel and
    re-publishes to the WebSocket broadcast channel + any configured webhooks.
    """
    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(_ALERT_CHANNEL)
    logger.info("Notification service subscribed to '%s'", _ALERT_CHANNEL)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            payload = json.loads(message["data"])
            await _dispatch(r, payload, webhook_urls or [])
        except Exception as exc:
            logger.error("Failed to dispatch alert: %s", exc)


async def _dispatch(
    r: aioredis.Redis,
    payload: dict,
    webhook_urls: list[str],
) -> None:
    """Forward the alert payload to WebSocket broadcast channel and webhooks."""
    # 1. Re-publish on the WebSocket broadcast channel for the api-gateway
    await r.publish(_WS_BROADCAST_CHANNEL, json.dumps(payload))

    # 2. Fire webhooks concurrently
    if webhook_urls:
        async with httpx.AsyncClient(timeout=5) as client:
            tasks = [_post_webhook(client, url, payload) for url in webhook_urls]
            await asyncio.gather(*tasks, return_exceptions=True)


async def _post_webhook(client: httpx.AsyncClient, url: str, payload: dict) -> None:
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        logger.debug("Webhook delivered to %s — status %d", url, resp.status_code)
    except Exception as exc:
        logger.warning("Webhook delivery failed for %s: %s", url, exc)
