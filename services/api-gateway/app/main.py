from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware import RequestLoggingMiddleware
from app.routers import (
    auth_router,
    deployments_router,
    feedback_router,
    outcomes_router,
    reports_router,
    users_router,
)
from shared.utils import init_db

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="LogPilot API Gateway",
    version="0.5.0",
    description="RBAC-protected gateway for LogPilot — Phase 5",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(reports_router)
app.include_router(outcomes_router)
app.include_router(deployments_router)
app.include_router(feedback_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/healthz")
def health():
    return {"status": "ok", "service": "api-gateway"}
