"""
Error Clustering Pipeline — Phase 3

Performs embedding-based DBSCAN clustering of deduplicated errors into
named clusters (error_clusters table).

Algorithm:
  1. Load all deduped_errors with embeddings for the service.
  2. Build a cosine-distance matrix.
  3. Run DBSCAN (epsilon = settings.clustering_eps, min_samples = settings.clustering_min_samples).
  4. For each new/changed cluster: compute centroid, calculate intra-cluster
     silhouette proxy (avg cosine similarity), and call the LLM to auto-label.
  5. Assign cluster_id back onto each deduped_error row.
  6. Mark clusters that no longer have members as is_active=False.

PRD §5 — Error Clustering Tool:
  embedding-based, density clustering, auto-labeled, confidence-scored.
Success criterion: clustering silhouette score > 0.65.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import DeduplicatedError, ErrorCluster
from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── math helpers ──────────────────────────────────────────────────────────────

def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Cosine distance (1 − cosine similarity), in [0, 2]."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 1.0
    return 1.0 - dot / (mag_a * mag_b)


def _centroid(embeddings: list[list[float]]) -> list[float]:
    """Element-wise mean of a list of vectors."""
    if not embeddings:
        return []
    dim = len(embeddings[0])
    total = [0.0] * dim
    for vec in embeddings:
        for i, v in enumerate(vec):
            total[i] += v
    n = len(embeddings)
    return [round(x / n, 6) for x in total]


def _avg_cosine_similarity(embeddings: list[list[float]], centroid_vec: list[float]) -> float:
    """
    Average cosine similarity of all members to the centroid.
    Used as a silhouette-score proxy (confidence_score).
    """
    if not embeddings or not centroid_vec:
        return 0.0
    total = 0.0
    for vec in embeddings:
        total += 1.0 - _cosine_distance(vec, centroid_vec)
    return round(total / len(embeddings), 4)


def _dbscan(
    embeddings: list[list[float]],
    eps: float,
    min_samples: int,
) -> list[int]:
    """
    Pure-Python DBSCAN on cosine distance.

    Returns a list of integer cluster labels (same length as embeddings).
    -1 = noise.  Labels start at 0.

    For large services the processing-worker can swap in sklearn's DBSCAN
    with metric='cosine'; this implementation is dependency-free for testing.
    """
    n = len(embeddings)
    labels = [-1] * n
    cluster_id = 0

    def neighbours(idx: int) -> list[int]:
        return [
            j for j in range(n)
            if j != idx and _cosine_distance(embeddings[idx], embeddings[j]) <= eps
        ]

    visited = [False] * n

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        nbrs = neighbours(i)

        if len(nbrs) < min_samples:
            continue   # noise (for now)

        # Start a new cluster
        labels[i] = cluster_id
        seed_set = list(nbrs)

        while seed_set:
            j = seed_set.pop()
            if not visited[j]:
                visited[j] = True
                j_nbrs = neighbours(j)
                if len(j_nbrs) >= min_samples:
                    seed_set.extend(j_nbrs)
            if labels[j] == -1:
                labels[j] = cluster_id

        cluster_id += 1

    return labels


# ── LLM auto-labelling ────────────────────────────────────────────────────────

async def _auto_label_cluster(
    messages: list[str],
    *,
    max_samples: int = 5,
) -> str:
    """
    Call the LLM provider to generate a short human-readable label for a cluster.
    Falls back to a rule-based label if AI is unavailable.
    """
    sample = messages[:max_samples]
    prompt = (
        "You are classifying error log messages into a cluster.\n"
        "Given these representative error messages:\n"
        + "\n".join(f"- {m}" for m in sample)
        + "\n\nRespond with a single short label (≤8 words) describing the common "
        "failure type. Be concise. Examples: 'Database connection timeout', "
        "'NullPointerException in checkout service', 'Redis cache miss storm'."
    )
    try:
        from app.providers import get_provider  # type: ignore[import]
        provider = get_provider()
        resp = await provider.complete(prompt, max_tokens=32)
        return resp.content.strip().strip('"').strip("'")[:512]
    except Exception as exc:
        logger.debug("LLM auto-label failed: %s — falling back to rule-based label", exc)

    # Rule-based fallback: take first 60 chars of the most common message prefix
    if sample:
        return sample[0][:60] + ("..." if len(sample[0]) > 60 else "")
    return "Unknown error cluster"


# ── public API ────────────────────────────────────────────────────────────────

async def run_clustering_pass(
    db: AsyncSession,
    service_id: uuid.UUID,
    *,
    eps: float | None = None,
    min_samples: int | None = None,
) -> dict:
    """
    Load all active deduped_errors for a service, run DBSCAN clustering,
    persist/update error_clusters rows, and back-assign cluster_id on each
    deduped_error.

    Returns a summary dict with cluster count and silhouette score.
    """
    _eps = eps if eps is not None else settings.clustering_eps
    _min_samples = min_samples if min_samples is not None else settings.clustering_min_samples

    # ── Load deduped errors with embeddings ───────────────────────────────────
    stmt = (
        select(DeduplicatedError)
        .where(
            DeduplicatedError.service_id == service_id,
            DeduplicatedError.embedding.isnot(None),
        )
    )
    result = await db.execute(stmt)
    errors: Sequence[DeduplicatedError] = result.scalars().all()

    if len(errors) < _min_samples:
        logger.info("Not enough embeddings to cluster for service %s (%d rows)", service_id, len(errors))
        return {"clusters": 0, "noise": 0, "silhouette_score": 0.0, "processed": len(errors)}

    embeddings = [e.embedding for e in errors]
    labels = _dbscan(embeddings, eps=_eps, min_samples=_min_samples)

    # ── Group errors by cluster label ─────────────────────────────────────────
    cluster_groups: dict[int, list[DeduplicatedError]] = {}
    for error, label in zip(errors, labels):
        cluster_groups.setdefault(label, []).append(error)

    now = datetime.now(timezone.utc)
    cluster_count = 0
    silhouette_scores: list[float] = []

    # ── Deactivate all existing clusters for this service first ───────────────
    await db.execute(
        update(ErrorCluster)
        .where(ErrorCluster.service_id == service_id)
        .values(is_active=False)
    )

    for label, members in cluster_groups.items():
        if label == -1:
            continue  # noise — skip cluster creation but still null out cluster_id

        member_embeddings = [m.embedding for m in members]
        centroid_vec = _centroid(member_embeddings)
        confidence = _avg_cosine_similarity(member_embeddings, centroid_vec)
        silhouette_scores.append(confidence)

        messages = [m.canonical_message for m in members]
        auto_label = await _auto_label_cluster(messages)

        first_seen = min(m.first_seen for m in members)
        last_seen = max(m.last_seen for m in members)

        # Upsert cluster (match on service_id + cluster_label)
        stmt_c = (
            select(ErrorCluster)
            .where(
                ErrorCluster.service_id == service_id,
                ErrorCluster.cluster_label == label,
            )
            .limit(1)
        )
        res_c = await db.execute(stmt_c)
        cluster: ErrorCluster | None = res_c.scalar_one_or_none()

        if cluster is None:
            cluster = ErrorCluster(
                id=uuid.uuid4(),
                service_id=service_id,
                cluster_label=label,
                auto_label=auto_label,
                confidence_score=confidence,
                member_count=len(members),
                centroid_embedding=centroid_vec,
                is_active=True,
                first_seen=first_seen,
                last_seen=last_seen,
            )
            db.add(cluster)
            await db.flush()
        else:
            cluster.auto_label = auto_label
            cluster.confidence_score = confidence
            cluster.member_count = len(members)
            cluster.centroid_embedding = centroid_vec
            cluster.is_active = True
            cluster.last_seen = last_seen

        await db.flush()

        # Assign cluster_id back onto member deduped_errors
        for member in members:
            member.cluster_id = cluster.id

        cluster_count += 1

    # Null out cluster_id for noise points
    noise_members = cluster_groups.get(-1, [])
    for member in noise_members:
        member.cluster_id = None

    await db.flush()

    avg_silhouette = (
        round(sum(silhouette_scores) / len(silhouette_scores), 4)
        if silhouette_scores else 0.0
    )

    logger.info(
        "Clustering pass: service=%s clusters=%d noise=%d silhouette=%.3f",
        service_id, cluster_count, len(noise_members), avg_silhouette,
    )

    return {
        "clusters": cluster_count,
        "noise": len(noise_members),
        "silhouette_score": avg_silhouette,
        "processed": len(errors),
    }
