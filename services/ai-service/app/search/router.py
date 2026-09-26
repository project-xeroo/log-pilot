"""
Search router — keyword and semantic log search endpoints.

GET  /search          — search log records
POST /search          — search log records (POST body for complex filters)
GET  /search/filters  — available filter values (services, environments, etc.)
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.search.engine import execute_search
from app.search.schemas import SearchMode, SearchRequest, SearchResponse

log = structlog.get_logger()
router = APIRouter(prefix="/search", tags=["search"])


# ---------------------------------------------------------------------------
# DB dependency — injected by the app
# ---------------------------------------------------------------------------

async def _get_db() -> AsyncSession:  # type: ignore[return]
    """Placeholder — overridden by app.dependency_overrides in main.py."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# POST /search  — primary search endpoint (full filter set via JSON body)
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=SearchResponse,
    summary="Search log records [Tool 02]",
    description=(
        "Search log records using keyword (FTS + regex) or semantic (vector similarity) mode. "
        "Supports filtering by time range, severity, service, environment, deployment version, "
        "and trace ID. Keyword search uses PostgreSQL FTS with the pg_trgm GIN index. "
        "Semantic search embeds the query via the cloud provider and runs pgvector k-NN."
    ),
)
async def search_post(
    request: SearchRequest,
    db: AsyncSession = Depends(_get_db),
) -> SearchResponse:
    return await execute_search(request, db)


# ---------------------------------------------------------------------------
# GET /search  — convenience endpoint (query params, no body required)
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=SearchResponse,
    summary="Search log records (GET) [Tool 02]",
)
async def search_get(
    q: str = Query(..., min_length=1, max_length=2000, description="Search query"),
    mode: SearchMode = Query(SearchMode.keyword),
    service_name: str | None = Query(None),
    environment: str | None = Query(None),
    severity: list[str] | None = Query(None),
    deployment_version: str | None = Query(None),
    trace_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(_get_db),
) -> SearchResponse:
    request = SearchRequest(
        query=q,
        mode=mode,
        service_name=service_name,
        environment=environment,
        severity=severity,
        deployment_version=deployment_version,
        trace_id=trace_id,
        limit=limit,
        offset=offset,
    )
    return await execute_search(request, db)


# ---------------------------------------------------------------------------
# GET /search/filters  — available filter values for the UI
# ---------------------------------------------------------------------------

@router.get(
    "/filters",
    summary="Get available filter values",
    description="Returns distinct services, environments, and severity levels in the DB.",
)
async def get_filters(db: AsyncSession = Depends(_get_db)) -> dict:
    """
    Returns the distinct values available for each filter dimension.
    Used by the frontend to populate filter dropdowns.
    """
    services_result = await db.execute(
        text("SELECT DISTINCT service_name FROM log_records WHERE service_name IS NOT NULL ORDER BY service_name LIMIT 200")
    )
    envs_result = await db.execute(
        text("SELECT DISTINCT environment FROM log_records WHERE environment IS NOT NULL ORDER BY environment LIMIT 100")
    )
    severities_result = await db.execute(
        text("SELECT DISTINCT severity::text FROM log_records ORDER BY severity::text")
    )
    versions_result = await db.execute(
        text("SELECT DISTINCT deployment_version FROM log_records WHERE deployment_version IS NOT NULL ORDER BY deployment_version LIMIT 100")
    )

    return {
        "services": [r[0] for r in services_result.all()],
        "environments": [r[0] for r in envs_result.all()],
        "severities": [r[0] for r in severities_result.all()],
        "deployment_versions": [r[0] for r in versions_result.all()],
    }
