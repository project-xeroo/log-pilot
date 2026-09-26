<<<<<<< HEAD
from __future__ import annotations

import logging
=======
"""
API Gateway — main FastAPI application.

Mounts:
  /forecasting  — forecasting router (risk, alerts, approvals, pre-mortems, policy)
  /audit        — audit router (agent_actions log)
  /ws/alerts    — WebSocket real-time alert stream
  /auth/token   — issue JWT tokens (dev/test helper)
  /health       — liveness check
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

<<<<<<< HEAD
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
=======
from app.routers.forecasting import router as forecasting_router
from app.websocket.alerts_ws import ws_endpoint, redis_broadcast_listener
from shared.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(redis_broadcast_listener())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="LogPilot API Gateway",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
)

app.add_middleware(
    CORSMiddleware,
<<<<<<< HEAD
    allow_origins=settings.cors_origins,
=======
    allow_origins=["*"],   # tighten in production
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
<<<<<<< HEAD
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
=======

app.include_router(forecasting_router)

# Import audit router from audit-service directly (same process in monorepo dev mode)
try:
    from services.audit_service.app.handlers.audit_router import router as audit_router
    app.include_router(audit_router)
except ImportError:
    pass   # audit-service runs as a separate container in production


# WebSocket endpoint
app.add_api_websocket_route("/ws/alerts", ws_endpoint)


# ── Dev helper: issue a JWT token ─────────────────────────────────────────────
from fastapi import APIRouter
from app.auth.jwt_auth import create_access_token, TokenResponse
from pydantic import BaseModel

_auth_router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    username: str
    role: str = "developer"


@_auth_router.post("/token", response_model=TokenResponse)
async def issue_token(body: TokenRequest):
    """
    Development-only token endpoint.
    In production this is replaced by your SSO / identity provider.
    """
    token = create_access_token(subject=body.username, role=body.role)
    return TokenResponse(access_token=token)


app.include_router(_auth_router)


@app.get("/health")
async def health():
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
    return {"status": "ok", "service": "api-gateway"}
