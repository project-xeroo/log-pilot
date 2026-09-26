"""
Search query engine — keyword (FTS + regex) and semantic (pgvector k-NN).

Keyword search:
  Uses PostgreSQL full-text search (tsvector GIN index on message_tsv) with
  optional regex fallback via pg_trgm. Filters are applied as WHERE clauses
  that exploit the composite indexes built in Phase 1.

Semantic search:
  Embeds the user query via the cloud provider, then runs a pgvector cosine
  similarity k-NN query against log_records.embedding (IVFFlat index).
  Filters are applied as pre-filter WHERE clauses before the ANN scan.

Performance targets (PRD §12):
  - Keyword search < 500 ms at 1 M+ records
  - Semantic search < 1 s at 1 M+ records
"""
from __future__ import annotations

import re
import time
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.providers import EmbeddingProvider
from app.search.schemas import (
    LogRecordResult,
    SearchMode,
    SearchRequest,
    SearchResponse,
)

log = structlog.get_logger()

_embedding_provider = EmbeddingProvider()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def execute_search(request: SearchRequest, db: AsyncSession) -> SearchResponse:
    """Dispatch to keyword or semantic engine based on request.mode."""
    t0 = time.perf_counter()

    if request.mode == SearchMode.semantic:
        results, total = await _semantic_search(request, db)
    else:
        results, total = await _keyword_search(request, db)

    latency_ms = (time.perf_counter() - t0) * 1000

    log.info(
        "search.executed",
        mode=request.mode,
        query_len=len(request.query),
        total=total,
        returned=len(results),
        latency_ms=round(latency_ms, 2),
    )

    return SearchResponse(
        query=request.query,
        mode=request.mode,
        total=total,
        results=results,
        latency_ms=round(latency_ms, 2),
    )


# ---------------------------------------------------------------------------
# Keyword / FTS search
# ---------------------------------------------------------------------------

async def _keyword_search(
    request: SearchRequest, db: AsyncSession
) -> tuple[list[LogRecordResult], int]:
    """
    Full-text search using PostgreSQL tsvector GIN index.
    Falls back to ILIKE regex scan if the query cannot be parsed as a tsquery.
    Filters applied via indexed WHERE clauses.
    """
    where, params = _build_filter_clauses(request)
    limit = min(request.limit, settings.search_max_results)
    offset = request.offset

    # Try to parse the query as a tsquery first (fast FTS path)
    use_fts = _is_safe_tsquery(request.query)

    if use_fts:
        # Convert query to plainto_tsquery for robustness (handles arbitrary text)
        where.append("message_tsv @@ plainto_tsquery('english', :fts_query)")
        params["fts_query"] = request.query
        order_by = "ts_rank(message_tsv, plainto_tsquery('english', :fts_query)) DESC, timestamp DESC"
    else:
        # Regex / pattern fallback — uses pg_trgm index on message when available
        safe_pattern = _sanitise_regex(request.query)
        where.append("message ~* :regex_pattern")
        params["regex_pattern"] = safe_pattern
        order_by = "timestamp DESC"

    where_clause = "WHERE " + " AND ".join(where) if where else ""

    count_sql = text(f"SELECT COUNT(*) FROM log_records {where_clause}")
    count_result = await db.execute(count_sql, params)
    total: int = count_result.scalar_one()

    rows_sql = text(f"""
        SELECT
            id, timestamp, service_name, severity, message, environment,
            deployment_version, trace_id, request_id, http_method, http_path,
            http_status, duration_ms, log_format, pii_was_redacted, extra_fields
        FROM log_records
        {where_clause}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """)
    params["limit"] = limit
    params["offset"] = offset

    rows_result = await db.execute(rows_sql, params)
    rows = rows_result.mappings().all()

    results = [_row_to_result(r) for r in rows]
    return results, total


# ---------------------------------------------------------------------------
# Semantic / vector search
# ---------------------------------------------------------------------------

async def _semantic_search(
    request: SearchRequest, db: AsyncSession
) -> tuple[list[LogRecordResult], int]:
    """
    Semantic search using pgvector cosine similarity.
    1. Embed the query via the cloud provider.
    2. Run ANN k-NN search on log_records.embedding with pre-filter WHERE clauses.
    3. Return results ordered by similarity score (descending).
    """
    # Embed the query
    query_vector = await _embedding_provider.embed_one(request.query)
    vector_literal = f"[{','.join(str(v) for v in query_vector)}]"

    where, params = _build_filter_clauses(request)
    # Exclude records with no embedding (not yet processed)
    where.append("embedding IS NOT NULL")

    where_clause = "WHERE " + " AND ".join(where) if where else ""
    limit = min(request.limit, settings.search_max_results)

    # pgvector cosine distance operator: <=> (lower = more similar)
    # We convert distance to a 0–1 similarity score: similarity = 1 - distance
    rows_sql = text(f"""
        SELECT
            id, timestamp, service_name, severity, message, environment,
            deployment_version, trace_id, request_id, http_method, http_path,
            http_status, duration_ms, log_format, pii_was_redacted, extra_fields,
            1 - (embedding <=> CAST(:query_vector AS vector)) AS similarity_score
        FROM log_records
        {where_clause}
        ORDER BY embedding <=> CAST(:query_vector AS vector)
        LIMIT :limit
    """)
    params["query_vector"] = vector_literal
    params["limit"] = limit

    rows_result = await db.execute(rows_sql, params)
    rows = rows_result.mappings().all()

    results = [_row_to_result(r, similarity_score=r.get("similarity_score")) for r in rows]
    # total is approximate for semantic search (we don't count all matching rows)
    return results, len(results)


# ---------------------------------------------------------------------------
# Shared filter builder
# ---------------------------------------------------------------------------

def _build_filter_clauses(request: SearchRequest) -> tuple[list[str], dict[str, Any]]:
    """
    Build parameterised WHERE clause fragments from the request filters.
    All conditions map to indexed columns.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if request.service_name:
        clauses.append("service_name = :service_name")
        params["service_name"] = request.service_name

    if request.environment:
        clauses.append("environment = :environment")
        params["environment"] = request.environment

    if request.deployment_version:
        clauses.append("deployment_version = :deployment_version")
        params["deployment_version"] = request.deployment_version

    if request.trace_id:
        clauses.append("trace_id = :trace_id")
        params["trace_id"] = request.trace_id

    if request.severity:
        # severity IN (:sev0, :sev1, ...)
        placeholders = ", ".join(f":sev_{i}" for i in range(len(request.severity)))
        clauses.append(f"severity::text IN ({placeholders})")
        for i, s in enumerate(request.severity):
            params[f"sev_{i}"] = s.upper()

    if request.time_from:
        clauses.append("timestamp >= :time_from")
        params["time_from"] = request.time_from

    if request.time_to:
        clauses.append("timestamp <= :time_to")
        params["time_to"] = request.time_to

    return clauses, params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_result(row: Any, similarity_score: float | None = None) -> LogRecordResult:
    return LogRecordResult(
        id=row["id"],
        timestamp=row["timestamp"],
        service_name=row["service_name"],
        severity=row["severity"],
        message=row["message"],
        environment=row["environment"],
        deployment_version=row["deployment_version"],
        trace_id=row["trace_id"],
        request_id=row["request_id"],
        http_method=row["http_method"],
        http_path=row["http_path"],
        http_status=row["http_status"],
        duration_ms=row["duration_ms"],
        log_format=row["log_format"],
        pii_was_redacted=row["pii_was_redacted"],
        extra_fields=row["extra_fields"],
        similarity_score=round(float(similarity_score), 4) if similarity_score is not None else None,
    )


def _is_safe_tsquery(query: str) -> bool:
    """Return True if the query is usable as a plainto_tsquery (no special regex chars)."""
    # plainto_tsquery handles arbitrary text; only exclude extremely short queries
    # that would return too many results or contain only punctuation.
    stripped = re.sub(r"[^\w\s]", "", query).strip()
    return len(stripped) >= 2


def _sanitise_regex(pattern: str) -> str:
    """
    Convert a user-supplied search string to a safe PostgreSQL regex pattern.
    If the string looks like a valid regex (contains regex meta-chars), use it
    as-is (PostgreSQL will raise if it's invalid). Otherwise treat it as a
    literal substring match.
    """
    regex_meta = r"[.^$*+?{}[\]\\|()]"
    if re.search(regex_meta, pattern):
        return pattern  # treat as regex
    return re.escape(pattern)  # literal
