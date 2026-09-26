"""
Leading indicator matcher.

Searches the vector store for historical failure embeddings that are
semantically similar to the current error cluster embedding for a service.
High similarity → the current pattern matches a known pre-failure signature
(PRD §4.1 — Leading Indicator Signals).

Returns:
- similarity_score  0-100  (used as the 40%-weight component in risk scoring)
- similar_past_event_ids   (list of matching alert IDs for alert citations)
- matched_pattern          (human-readable label of the closest match)
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_TOP_K = 5           # number of nearest neighbours to retrieve
_MATCH_THRESHOLD = 0.75  # minimum cosine similarity to count as a "match"


async def find_similar_incidents(
    db: AsyncSession,
    service_id: uuid.UUID,
    current_embedding: list[float],
    top_k: int = _TOP_K,
) -> dict:
    """
    Run a k-NN cosine similarity search over *leading_indicator_embeddings*
    for the given service.

    Returns a dict with:
      "similarity_score"      float 0-100
      "similar_past_event_ids" list[str]
      "matched_pattern"        str | None
      "confidence"             float 0-1
    """
    # pgvector cosine distance = 1 - cosine_similarity; lower = more similar
    stmt = text("""
        SELECT
            id,
            alert_id,
            label,
            1 - (embedding <=> :embedding::vector) AS similarity
        FROM leading_indicator_embeddings
        WHERE service_id = :service_id
        ORDER BY embedding <=> :embedding::vector
        LIMIT :top_k
    """)
    result = await db.execute(stmt, {
        "service_id": str(service_id),
        "embedding": current_embedding,
        "top_k": top_k,
    })
    rows = result.fetchall()

    if not rows:
        return {
            "similarity_score": 0.0,
            "similar_past_event_ids": [],
            "matched_pattern": None,
            "confidence": 0.0,
        }

    # Only count matches above the threshold
    matches = [r for r in rows if r.similarity >= _MATCH_THRESHOLD]

    if not matches:
        return {
            "similarity_score": 0.0,
            "similar_past_event_ids": [],
            "matched_pattern": None,
            "confidence": 0.0,
        }

    best = matches[0]
    avg_similarity = sum(r.similarity for r in matches) / len(matches)

    # Map average similarity [0.75, 1.0] → score [0, 100]
    normalised = ((avg_similarity - _MATCH_THRESHOLD) / (1.0 - _MATCH_THRESHOLD)) * 100.0
    similarity_score = round(min(normalised, 100.0), 2)

    return {
        "similarity_score": similarity_score,
        "similar_past_event_ids": [str(r.alert_id) for r in matches if r.alert_id],
        "matched_pattern": best.label,
        "confidence": round(float(best.similarity), 4),
    }
