"""
LogPilot AI Service — FastAPI application.

  - Model-agnostic OpenAI-compatible provider layer (app/providers/)
  - Semantic + keyword log search  (app/search/)
  - Conversational chat with source citations (app/chat/)
  - Agent feed endpoint (app/feed/)
  - Incident report drafting (app/reports/)

  - RCA and deployment comparison endpoints (app/analysis_api.py)

Anomaly detection and analytics (app/anomaly, app/analytics) are libraries
invoked by the processing worker's analysis pipeline.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# DB engine (read/search queries against the shared logpilot DB)
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
    app.state.db_factory = _SessionLocal
    log.info("ai_service.startup", service=settings.service_name)
    # Validate that the provider is reachable on startup (warn-only, don't block)
    if settings.use_stub_provider:
        log.warning(
            "ai_service.stub_provider",
            detail="No OPENAI_API_KEY (or AI_PROVIDER=stub) — using the offline stub provider.",
        )
    yield
    await _engine.dispose()
    log.info("ai_service.shutdown")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LogPilot AI Service",
    description=(
        "Phase 2 — Core Agent Interface.\n\n"
        "Provides semantic search, keyword search, conversational chat with "
        "source citations, and the agent feed stream. All AI inference routes "
        "through a model-agnostic OpenAI-compatible provider layer."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.search.router import router as search_router, _get_db as _search_get_db  # noqa: E402
from app.chat.router import router as chat_router, _get_db as _chat_get_db        # noqa: E402
from app.feed.router import router as feed_router, _get_db as _feed_get_db        # noqa: E402
from app.reports import router as reports_router                                  # noqa: E402
from app.analysis_api import router as analysis_router, _get_db as _analysis_get_db  # noqa: E402

app.include_router(search_router)
app.include_router(chat_router)
app.include_router(feed_router)
app.include_router(reports_router)
app.include_router(analysis_router)

# Wire each router's DB dependency to the app's session factory
app.dependency_overrides[_search_get_db] = get_db
app.dependency_overrides[_chat_get_db] = get_db
app.dependency_overrides[_feed_get_db] = get_db
app.dependency_overrides[_analysis_get_db] = get_db


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
@app.get("/healthz", tags=["ops"], include_in_schema=False)
async def health():
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": "2.0.0",
        "provider": "stub" if settings.use_stub_provider else settings.ai_provider,
        "embedding_model": settings.embedding_model,
        "chat_model": settings.chat_model,
        "reasoning_model": settings.reasoning_model,
    }
