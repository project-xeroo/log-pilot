"""
Search request/response schemas.
Shared between the router (HTTP layer) and the query engine (DB layer).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    keyword = "keyword"
    semantic = "semantic"


class SearchRequest(BaseModel):
    """Unified search request — supports both keyword and semantic modes."""

    query: str = Field(..., min_length=1, max_length=2000, description="Search query text")
    mode: SearchMode = Field(SearchMode.keyword, description="keyword or semantic")

    # ── Filters (all optional) ───────────────────────────────────────────────
    service_name: str | None = Field(None, description="Filter by service name (exact)")
    environment: str | None = Field(None, description="Filter by environment (exact)")
    severity: list[str] | None = Field(None, description="One or more severity levels")
    deployment_version: str | None = Field(None, description="Filter by deployment version")
    trace_id: str | None = Field(None, description="Filter by trace ID (exact)")

    time_from: datetime | None = Field(None, description="Start of time range (inclusive)")
    time_to: datetime | None = Field(None, description="End of time range (inclusive)")

    limit: int = Field(20, ge=1, le=100, description="Max results to return")
    offset: int = Field(0, ge=0, description="Pagination offset (keyword mode only)")


class LogRecordResult(BaseModel):
    """One matching log record returned in search results."""

    id: int
    timestamp: datetime | None
    service_name: str | None
    severity: str
    message: str | None
    environment: str | None
    deployment_version: str | None
    trace_id: str | None
    request_id: str | None
    http_method: str | None
    http_path: str | None
    http_status: int | None
    duration_ms: float | None
    log_format: str
    pii_was_redacted: bool
    extra_fields: dict[str, Any] | None

    # Semantic search only
    similarity_score: float | None = None

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Search response envelope."""

    query: str
    mode: SearchMode
    total: int                          # exact count for keyword; approximate for semantic
    results: list[LogRecordResult]
    latency_ms: float                   # server-side query latency
