"""
Notification service FastAPI entrypoint.
Starts the Redis alert subscriber as a background task on startup.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.channels.publisher import subscribe_and_dispatch
from shared.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the subscriber loop on service startup
    task = asyncio.create_task(subscribe_and_dispatch())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="LogPilot Notification Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification-service"}
