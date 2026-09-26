"""
Agent API Gateway — FastAPI application.

Phase 1 skeleton:
  - JWT authentication (login / register)
  - RBAC on all protected endpoints
  - Audit logging middleware (agent_actions)
  - Proxy routers to downstream services
  - WebSocket scaffold
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.middleware import AuditLoggingMiddleware
from app.routers.auth import router as auth_router
from app.routers.ingestion import router as ingestion_router

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# DB engine
# ---------------------------------------------------------------------------
_engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)
_SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Make DB factory available to middleware
    app.state.db_factory = _SessionLocal
    log.info("api_gateway.startup", service=settings.service_name)
    yield
    await _engine.dispose()
    log.info("api_gateway.shutdown")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LogPilot Agent API",
    description=(
        "Phase 1 — Cloud Foundation & Data Ingestion Pipeline.\n\n"
        "All endpoints are RBAC-protected. Every action is audit-logged. "
        "PII redaction is enforced at the ingestion layer before storage."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — tighten in production to specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audit logging — every request by authenticated users
app.add_middleware(AuditLoggingMiddleware)

# Override DB dependency for routers
app.dependency_overrides[get_db] = get_db  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(ingestion_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health():
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": "0.1.0",
        "phase": "1",
    }
