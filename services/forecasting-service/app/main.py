<<<<<<< HEAD
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.loop import router as feedback_router
from shared.utils import init_db

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="LogPilot Forecasting Service",
    version="0.5.0",
    description="Leading-indicator scoring and outcome-driven feedback loop",
)

app.include_router(feedback_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/healthz")
def health():
=======
"""Forecasting service — FastAPI health endpoint + Celery entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="LogPilot Forecasting Service", version="1.0.0")


@app.get("/health")
async def health():
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
    return {"status": "ok", "service": "forecasting-service"}
