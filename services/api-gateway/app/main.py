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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {"status": "ok", "service": "api-gateway"}
