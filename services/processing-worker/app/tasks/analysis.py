"""
Phase 3 Analysis Pipeline Celery Tasks.

Scheduled tasks:
  analysis.run_dedup_for_service    — runs deduplication pass for one service
  analysis.run_clustering_for_service — runs clustering pass for one service
  analysis.run_analysis_pipeline    — orchestrates dedup → cluster → health update
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import AsyncSessionLocal
from shared.models import MonitoredService

logger = logging.getLogger(__name__)


async def _run_analysis_for_service(service: MonitoredService, db: AsyncSession) -> dict:
    """Execute the full dedup → cluster → health-state update cycle."""
    from app.deduplication import run_dedup_pass
    from app.clustering import run_clustering_pass

    service_id: uuid.UUID = service.id

    dedup_stats = await run_dedup_pass(db, service_id)
    cluster_stats = await run_clustering_pass(db, service_id)

    # Update service health state
    await _update_health_state(db, service_id)

    await db.commit()

    return {
        "service": service.name,
        "dedup": dedup_stats,
        "clustering": cluster_stats,
    }


async def _update_health_state(db: AsyncSession, service_id: uuid.UUID) -> None:
    """
    Recompute and upsert the ServiceHealthState row for this service.
    Called at the end of every analysis cycle.
    """
    from sqlalchemy import text, func
    from shared.models import (
        ServiceHealthState,
        DeduplicatedError,
        ErrorCluster,
        AnomalyEvent,
        RiskSnapshot,
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    # ── Count active clusters ─────────────────────────────────────────────────
    cluster_count_stmt = select(func.count()).where(
        ErrorCluster.service_id == service_id,
        ErrorCluster.is_active == True,  # noqa: E712
    )
    active_clusters = (await db.execute(cluster_count_stmt)).scalar() or 0

    # ── Count total deduped errors ────────────────────────────────────────────
    dedup_count_stmt = select(func.count()).where(DeduplicatedError.service_id == service_id)
    total_deduped = (await db.execute(dedup_count_stmt)).scalar() or 0

    # ── Count open anomalies ──────────────────────────────────────────────────
    anomaly_count_stmt = select(func.count()).where(
        AnomalyEvent.service_id == service_id,
        AnomalyEvent.is_resolved == False,  # noqa: E712
    )
    open_anomalies = (await db.execute(anomaly_count_stmt)).scalar() or 0

    # ── Get top cluster label ─────────────────────────────────────────────────
    top_cluster_stmt = (
        select(ErrorCluster.auto_label)
        .where(ErrorCluster.service_id == service_id, ErrorCluster.is_active == True)  # noqa: E712
        .order_by(ErrorCluster.member_count.desc())
        .limit(1)
    )
    top_cluster_result = await db.execute(top_cluster_stmt)
    top_label = top_cluster_result.scalar_one_or_none()

    # ── Get latest risk snapshot ──────────────────────────────────────────────
    from sqlalchemy import desc
    risk_stmt = (
        select(RiskSnapshot)
        .where(RiskSnapshot.service_id == service_id)
        .order_by(desc(RiskSnapshot.evaluated_at))
        .limit(1)
    )
    risk_result = await db.execute(risk_stmt)
    latest_risk = risk_result.scalar_one_or_none()
    risk_tier = latest_risk.risk_tier if latest_risk else "normal"
    risk_score = latest_risk.risk_score if latest_risk else 0.0

    # ── Compute composite health score (0–100, higher = healthier) ───────────
    # Penalise for each risk tier level, open anomalies, and active clusters
    health_score = 100.0
    if risk_tier == "warning":
        health_score -= 20.0
    elif risk_tier == "critical":
        health_score -= 50.0
    health_score -= min(open_anomalies * 5.0, 30.0)
    health_score -= min(active_clusters * 2.0, 20.0)
    health_score = max(health_score, 0.0)

    # ── Upsert ServiceHealthState ─────────────────────────────────────────────
    stmt = select(ServiceHealthState).where(ServiceHealthState.service_id == service_id).limit(1)
    result = await db.execute(stmt)
    health_state = result.scalar_one_or_none()

    if health_state is None:
        health_state = ServiceHealthState(
            id=uuid.uuid4(),
            service_id=service_id,
            health_score=health_score,
            baseline_error_rate=0.0,
            current_error_rate=0.0,
            baseline_deviation_z=0.0,
            active_cluster_count=active_clusters,
            total_deduped_error_count=total_deduped,
            open_anomaly_count=open_anomalies,
            top_cluster_label=top_label,
            latest_risk_tier=risk_tier,
            latest_risk_score=risk_score,
            evaluated_at=now,
        )
        db.add(health_state)
    else:
        health_state.health_score = health_score
        health_state.active_cluster_count = active_clusters
        health_state.total_deduped_error_count = total_deduped
        health_state.open_anomaly_count = open_anomalies
        health_state.top_cluster_label = top_label
        health_state.latest_risk_tier = risk_tier
        health_state.latest_risk_score = risk_score
        health_state.evaluated_at = now

    await db.flush()


# ── Celery task entry points ──────────────────────────────────────────────────

@shared_task(
    name="analysis.run_analysis_pipeline",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_analysis_pipeline(self, service_id: str) -> dict:
    """
    Celery task: run dedup → cluster → health-state update for one service.
    Called after every log ingestion batch and on a scheduled interval.
    """
    async def _inner():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MonitoredService).where(MonitoredService.id == uuid.UUID(service_id))
            )
            service = result.scalar_one_or_none()
            if service is None or not service.is_active:
                return {"status": "skipped", "reason": "service not found or inactive"}
            stats = await _run_analysis_for_service(service, db)
            return {"status": "ok", **stats}

    try:
        return asyncio.get_event_loop().run_until_complete(_inner())
    except Exception as exc:
        logger.error("Analysis pipeline failed for service %s: %s", service_id, exc)
        raise self.retry(exc=exc)
