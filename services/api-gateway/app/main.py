"""
API Gateway — main FastAPI application (RBAC-protected entry point for the console).

Mounts:
  /auth         — JWT login, register, and current-user profile
  /ingest       — log ingestion proxy
  /search       — semantic + keyword search proxy
  /chat         — conversational chat proxy (streaming SSE passthrough)
  /feed         — agent feed proxy
  /forecasting  — forecasting router (risk, alerts, approvals, pre-mortems, policy)
  /analysis     — analysis router (dedup, clusters, health, rca, anomalies, deployment comparison)
  /reports      — incident reports (draft, edit, export)
  /outcomes     — incident outcome feedback
  /deployments  — deployment snapshots and comparison
  /feedback     — forecasting weight observability
  /users        — user and role management
  /audit        — audit router (agent_actions log)
  /ws           — WebSocket for real-time feed and alert events
  /health       — liveness check
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware import AuditLoggingMiddleware
from app.routers.analysis import router as analysis_router
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.deployments import router as deployments_router
from app.routers.feed import router as feed_router
from app.routers.feedback import router as feedback_router
from app.routers.forecasting import router as forecasting_router
from app.routers.ingestion import router as ingestion_router
from app.routers.outcomes import router as outcomes_router
from app.routers.reports import router as reports_router
from app.routers.search import router as search_router
from app.routers.users import router as users_router
from app.websocket import redis_event_relay
from app.websocket.router import router as ws_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    relay = asyncio.create_task(redis_event_relay())
    yield
    relay.cancel()
    try:
        await relay
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # relay may already have failed (e.g. Redis down)
        log.warning("ws.relay.stopped", error=str(exc))


app = FastAPI(
    title="LogPilot API Gateway",
    description="RBAC-protected gateway for the LogPilot supervisory console",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLoggingMiddleware)

# Core agent interface
app.include_router(auth_router)
app.include_router(ingestion_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(feed_router)
app.include_router(ws_router)
# Forecasting & analysis
app.include_router(forecasting_router)
app.include_router(analysis_router)
# Reporting, feedback & administration
app.include_router(reports_router)
app.include_router(outcomes_router)
app.include_router(deployments_router)
app.include_router(feedback_router)
app.include_router(users_router)

# Import audit router from audit-service directly (same process in monorepo dev mode)
try:
    from services.audit_service.app.handlers.audit_router import router as audit_router
    app.include_router(audit_router)
except ImportError:
    pass   # audit-service runs as a separate container in production


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "service": "api-gateway"}
