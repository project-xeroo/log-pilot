"""
Pattern drift detector.

Uses pgvector cosine similarity to detect when the current error cluster
centroid has shifted away from the established baseline centroid for a
service (PRD §4.1 — Pattern Drift Detection).

When a cluster's centroid shifts, the system is entering failure modes
it hasn't fully expressed yet — detectable only through embeddings, not
keyword-based monitoring.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_RECENT_WINDOW = 20      # how many recent embeddings define the "current" cluster
_BASELINE_WINDOW = 100   # how many older embeddings define the baseline


async def _fetch_mean_embedding(
    db: AsyncSession,
    service_id: uuid.UUID,
    limit: int,
    offset: int = 0,
) -> list[float] | None:
    """
    Return the mean (centroid) of the *limit* most-recent embeddings for a
    service, skipping *offset* rows.  Returns None if no embeddings exist.
    """
    stmt = text("""
        SELECT AVG(embedding) AS centroid
        FROM (
            SELECT embedding
            FROM leading_indicator_embeddings
            WHERE service_id = :service_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        ) sub
    """)
    result = await db.execute(stmt, {"service_id": str(service_id), "limit": limit, "offset": offset})
    row = result.fetchone()
    if row is None or row[0] is None:
        return None
    # pgvector returns the vector as a list already
    return list(row[0])


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x ** 2 for x in a) ** 0.5
    norm_b = sum(x ** 2 for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0   # identical zero vectors → no drift
    return dot / (norm_a * norm_b)


async def compute_drift_score(
    db: AsyncSession,
    service_id: uuid.UUID,
) -> float:
    """
    Compare the centroid of the most-recent embeddings against the centroid
    of the prior baseline window.  Return a 0-100 drift score where:
      0   = no drift (cosine similarity = 1.0)
      100 = maximum drift (cosine similarity ≤ 0)

    If there is insufficient embedding history, returns 0.0 (safe default).
    """
    recent_centroid = await _fetch_mean_embedding(db, service_id, limit=_RECENT_WINDOW, offset=0)
    if recent_centroid is None:
        return 0.0

    baseline_centroid = await _fetch_mean_embedding(
        db, service_id, limit=_BASELINE_WINDOW, offset=_RECENT_WINDOW
    )
    if baseline_centroid is None:
        return 0.0

    similarity = _cosine_similarity(recent_centroid, baseline_centroid)
    # similarity: 1.0 = identical, 0.0 = orthogonal, -1.0 = opposite
    # Map to drift score: (1 - similarity) * 100, clamped to [0, 100]
    drift = max((1.0 - similarity) * 100.0, 0.0)
    return round(min(drift, 100.0), 2)


async def store_embedding(
    db: AsyncSession,
    service_id: uuid.UUID,
    embedding: list[float],
    alert_id: uuid.UUID | None = None,
    label: str | None = None,
) -> None:
    """
    Persist one embedding vector for a service error pattern.
    Called by the processing-worker after generating embeddings for new log clusters.
    """
    stmt = text("""
        INSERT INTO leading_indicator_embeddings
            (id, service_id, alert_id, embedding, label, created_at)
        VALUES
            (gen_random_uuid(), :service_id, :alert_id, :embedding, :label, now())
    """)
    await db.execute(stmt, {
        "service_id": str(service_id),
        "alert_id": str(alert_id) if alert_id else None,
        "embedding": embedding,
        "label": label,
    })
    await db.flush()
