"""
Error Deduplication Pipeline — Phase 3

Performs semantic-similarity grouping of raw log error messages into
deduplicated error groups (deduped_errors table).

Algorithm:
  1. For each new log record batch (per service), generate an embedding vector.
  2. Compare against existing deduped_error centroids for the same service using
     cosine similarity.
  3. If similarity ≥ SIMILARITY_THRESHOLD: increment occurrence_count, update
     last_seen, and update the centroid (exponential moving average).
  4. If similarity < threshold (or no existing group): create a new deduped_error.
  5. A SHA-256 fingerprint of the normalised message provides fast exact-match
     short-circuit before hitting the similarity path.

PRD §5 — Error Deduplication Tool:
  semantic-similarity grouping with occurrence counts and first/last-seen timestamps.
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import DeduplicatedError, MonitoredService
from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── helpers ───────────────────────────────────────────────────────────────────

def _normalise_message(message: str) -> str:
    """
    Strip dynamic tokens (UUIDs, hex IDs, numbers, IPs, timestamps) so that
    semantically identical errors with different IDs produce the same fingerprint.
    """
    import re
    text = message
    # UUIDs
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", text, flags=re.I)
    # Hex IDs / hashes
    text = re.sub(r"\b[0-9a-f]{16,}\b", "<hex>", text, flags=re.I)
    # IPv4
    text = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "<ip>", text)
    # Standalone numbers (but not short ones in words)
    text = re.sub(r"\b\d{4,}\b", "<num>", text)
    return text.strip().lower()


def _fingerprint(message: str) -> str:
    """SHA-256 hex digest of the normalised message (truncated to 64 chars)."""
    normalised = _normalise_message(message)
    return hashlib.sha256(normalised.encode()).hexdigest()[:64]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _update_centroid(
    current: list[float],
    new: list[float],
    count: int,
    alpha: float = 0.1,
) -> list[float]:
    """
    Exponential moving average update of the centroid.
    alpha controls how much the new vector shifts the centroid.
    """
    return [round((1 - alpha) * c + alpha * n, 6) for c, n in zip(current, new)]


# ── public API ────────────────────────────────────────────────────────────────

async def dedup_error(
    db: AsyncSession,
    service_id: uuid.UUID,
    message: str,
    severity: str,
    embedding: list[float],
    occurred_at: datetime,
    source_record_id: str | None = None,
    similarity_threshold: float | None = None,
) -> DeduplicatedError:
    """
    Find an existing deduped group for this error or create a new one.
    Returns the (updated or created) DeduplicatedError row.
    """
    threshold = similarity_threshold or settings.dedup_similarity_threshold
    fp = _fingerprint(message)

    # ── 1. Fast exact-match via fingerprint ───────────────────────────────────
    stmt = (
        select(DeduplicatedError)
        .where(
            DeduplicatedError.service_id == service_id,
            DeduplicatedError.fingerprint == fp,
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # Update count and timestamps
        existing.occurrence_count += 1
        existing.last_seen = max(existing.last_seen, occurred_at)
        if embedding and existing.embedding:
            existing.embedding = _update_centroid(
                existing.embedding, embedding, existing.occurrence_count
            )
        if source_record_id:
            ids: list = existing.source_record_ids or []
            if source_record_id not in ids:
                ids.append(source_record_id)
                existing.source_record_ids = ids
        await db.flush()
        return existing

    # ── 2. Semantic similarity scan (recent 200 groups for this service) ──────
    if embedding:
        stmt2 = (
            select(DeduplicatedError)
            .where(DeduplicatedError.service_id == service_id)
            .order_by(desc(DeduplicatedError.last_seen))
            .limit(200)
        )
        result2 = await db.execute(stmt2)
        candidates: Sequence[DeduplicatedError] = result2.scalars().all()

        best_match: DeduplicatedError | None = None
        best_score = 0.0
        for candidate in candidates:
            if not candidate.embedding:
                continue
            score = _cosine_similarity(embedding, candidate.embedding)
            if score > best_score:
                best_score = score
                best_match = candidate

        if best_match and best_score >= threshold:
            best_match.occurrence_count += 1
            best_match.last_seen = max(best_match.last_seen, occurred_at)
            best_match.embedding = _update_centroid(
                best_match.embedding, embedding, best_match.occurrence_count
            )
            if source_record_id:
                ids = best_match.source_record_ids or []
                if source_record_id not in ids:
                    ids.append(source_record_id)
                    best_match.source_record_ids = ids
            await db.flush()
            return best_match

    # ── 3. No match — create new deduped group ────────────────────────────────
    deduped = DeduplicatedError(
        id=uuid.uuid4(),
        service_id=service_id,
        fingerprint=fp,
        canonical_message=message,
        severity=severity,
        occurrence_count=1,
        first_seen=occurred_at,
        last_seen=occurred_at,
        embedding=embedding,
        source_record_ids=[source_record_id] if source_record_id else [],
    )
    db.add(deduped)
    await db.flush()
    return deduped


async def run_dedup_pass(
    db: AsyncSession,
    service_id: uuid.UUID,
    *,
    lookback_minutes: int = 60,
) -> dict:
    """
    Background pass: re-evaluate raw log_records for a service over the last
    lookback_minutes and upsert into deduped_errors.

    Called by the Celery pipeline task after each log ingestion.
    Returns summary stats.
    """
    from sqlalchemy import text

    cutoff = datetime.now(timezone.utc)
    cutoff_str = cutoff.isoformat()

    stmt = text("""
        SELECT id, message, severity, timestamp
        FROM log_records
        WHERE service_name = (
            SELECT name FROM monitored_services WHERE id = :service_id
        )
        AND severity IN ('ERROR', 'CRITICAL', 'FATAL')
        AND timestamp >= NOW() - INTERVAL '1 minute' * :lookback
        ORDER BY timestamp DESC
        LIMIT 1000
    """)
    result = await db.execute(stmt, {"service_id": str(service_id), "lookback": lookback_minutes})
    rows = result.fetchall()

    if not rows:
        return {"processed": 0, "new_groups": 0, "merged": 0}

    # We don't call the AI embedding provider here — embeddings are pre-computed
    # during the ingestion pipeline and stored. For rows missing embeddings we
    # fall back to fingerprint-only dedup.
    new_groups = 0
    merged = 0

    for row in rows:
        record_id = str(row.id)
        fp = _fingerprint(row.message or "")

        stmt_existing = (
            select(DeduplicatedError)
            .where(
                DeduplicatedError.service_id == service_id,
                DeduplicatedError.fingerprint == fp,
            )
            .limit(1)
        )
        res = await db.execute(stmt_existing)
        existing = res.scalar_one_or_none()
        occurred_at = row.timestamp or datetime.now(timezone.utc)

        if existing:
            existing.occurrence_count += 1
            existing.last_seen = max(existing.last_seen, occurred_at)
            ids = existing.source_record_ids or []
            if record_id not in ids:
                ids.append(record_id)
                existing.source_record_ids = ids
            merged += 1
        else:
            db.add(DeduplicatedError(
                id=uuid.uuid4(),
                service_id=service_id,
                fingerprint=fp,
                canonical_message=row.message or "",
                severity=row.severity or "ERROR",
                occurrence_count=1,
                first_seen=occurred_at,
                last_seen=occurred_at,
                source_record_ids=[record_id],
            ))
            new_groups += 1

    await db.flush()
    return {"processed": len(rows), "new_groups": new_groups, "merged": merged}
