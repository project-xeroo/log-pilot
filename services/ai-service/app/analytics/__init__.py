"""
Analytics / Health-State Tool — Phase 3

PRD §5: Analytics / Health-State Tool
  read-only, continuously updated per-service health state.

Provides:
  - get_health_state(service_id) → ServiceHealthStateResult  (< 3 seconds target)
  - list_health_states() → list[ServiceHealthStateResult]    (all services)
  - get_health_summary() → fleet-wide aggregate

The ServiceHealthState table is maintained by the analysis pipeline
(services/processing-worker/app/tasks/analysis.py).  This module only reads.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import (
    ServiceHealthState,
    MonitoredService,
    AnomalyEvent,
    ErrorCluster,
    DeduplicatedError,
    RiskSnapshot,
)


# ── Output schemas ────────────────────────────────────────────────────────────

@dataclass
class ServiceHealthStateResult:
    service_id: str
    service_name: str
    health_score: float
    baseline_error_rate: float
    current_error_rate: float
    baseline_deviation_z: float
    active_cluster_count: int
    total_deduped_error_count: int
    open_anomaly_count: int
    top_cluster_label: str | None
    latest_risk_tier: str
    latest_risk_score: float
    evaluated_at: str
    # Recent anomaly summaries (up to 3)
    recent_anomalies: list[dict[str, Any]] = field(default_factory=list)
    # Top clusters
    top_clusters: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FleetHealthSummary:
    total_services: int
    healthy_count: int      # health_score >= 80
    warning_count: int      # health_score 50–79
    critical_count: int     # health_score < 50
    total_open_anomalies: int
    total_active_clusters: int
    most_at_risk_service: str | None
    evaluated_at: str


# ── Queries ───────────────────────────────────────────────────────────────────

async def get_health_state(
    db: AsyncSession,
    service_id: uuid.UUID,
) -> ServiceHealthStateResult | None:
    """
    Retrieve the current health state for a single service.
    Returns None if no health state exists yet.
    Performance target: < 3 seconds (PRD success criterion).
    """
    # ── Primary health state row ──────────────────────────────────────────────
    result = await db.execute(
        select(ServiceHealthState, MonitoredService)
        .join(MonitoredService, MonitoredService.id == ServiceHealthState.service_id)
        .where(ServiceHealthState.service_id == service_id)
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None

    health_state, service = row

    # ── Recent anomalies ──────────────────────────────────────────────────────
    anomaly_result = await db.execute(
        select(AnomalyEvent)
        .where(AnomalyEvent.service_id == service_id, AnomalyEvent.is_resolved == False)  # noqa: E712
        .order_by(desc(AnomalyEvent.detected_at))
        .limit(3)
    )
    recent_anomalies = [
        {
            "type": a.anomaly_type,
            "explanation": a.explanation,
            "severity": a.severity,
            "detected_at": a.detected_at.isoformat() if a.detected_at else None,
        }
        for a in anomaly_result.scalars().all()
    ]

    # ── Top clusters ──────────────────────────────────────────────────────────
    cluster_result = await db.execute(
        select(ErrorCluster)
        .where(ErrorCluster.service_id == service_id, ErrorCluster.is_active == True)  # noqa: E712
        .order_by(desc(ErrorCluster.member_count))
        .limit(5)
    )
    top_clusters = [
        {
            "id": str(c.id),
            "label": c.auto_label,
            "member_count": c.member_count,
            "confidence_score": c.confidence_score,
            "first_seen": c.first_seen.isoformat() if c.first_seen else None,
            "last_seen": c.last_seen.isoformat() if c.last_seen else None,
        }
        for c in cluster_result.scalars().all()
    ]

    return ServiceHealthStateResult(
        service_id=str(health_state.service_id),
        service_name=service.name,
        health_score=health_state.health_score,
        baseline_error_rate=health_state.baseline_error_rate,
        current_error_rate=health_state.current_error_rate,
        baseline_deviation_z=health_state.baseline_deviation_z,
        active_cluster_count=health_state.active_cluster_count,
        total_deduped_error_count=health_state.total_deduped_error_count,
        open_anomaly_count=health_state.open_anomaly_count,
        top_cluster_label=health_state.top_cluster_label,
        latest_risk_tier=health_state.latest_risk_tier,
        latest_risk_score=health_state.latest_risk_score,
        evaluated_at=health_state.evaluated_at.isoformat() if health_state.evaluated_at else "",
        recent_anomalies=recent_anomalies,
        top_clusters=top_clusters,
    )


async def list_health_states(
    db: AsyncSession,
    *,
    active_only: bool = True,
) -> list[ServiceHealthStateResult]:
    """
    Return health states for all (active) services.
    Ordered by health_score ascending (worst first).
    """
    stmt = (
        select(ServiceHealthState, MonitoredService)
        .join(MonitoredService, MonitoredService.id == ServiceHealthState.service_id)
    )
    if active_only:
        stmt = stmt.where(MonitoredService.is_active == True)  # noqa: E712
    stmt = stmt.order_by(ServiceHealthState.health_score.asc())

    result = await db.execute(stmt)
    rows = result.all()

    states = []
    for health_state, service in rows:
        states.append(ServiceHealthStateResult(
            service_id=str(health_state.service_id),
            service_name=service.name,
            health_score=health_state.health_score,
            baseline_error_rate=health_state.baseline_error_rate,
            current_error_rate=health_state.current_error_rate,
            baseline_deviation_z=health_state.baseline_deviation_z,
            active_cluster_count=health_state.active_cluster_count,
            total_deduped_error_count=health_state.total_deduped_error_count,
            open_anomaly_count=health_state.open_anomaly_count,
            top_cluster_label=health_state.top_cluster_label,
            latest_risk_tier=health_state.latest_risk_tier,
            latest_risk_score=health_state.latest_risk_score,
            evaluated_at=health_state.evaluated_at.isoformat() if health_state.evaluated_at else "",
        ))
    return states


async def get_fleet_health_summary(db: AsyncSession) -> FleetHealthSummary:
    """Return a fleet-wide aggregate health summary."""
    stmt = (
        select(ServiceHealthState, MonitoredService)
        .join(MonitoredService, MonitoredService.id == ServiceHealthState.service_id)
        .where(MonitoredService.is_active == True)  # noqa: E712
    )
    result = await db.execute(stmt)
    rows = result.all()

    total = len(rows)
    healthy = warning = critical = 0
    total_anomalies = 0
    total_clusters = 0
    worst_service: str | None = None
    worst_score = 101.0

    for health_state, service in rows:
        score = health_state.health_score
        if score >= 80:
            healthy += 1
        elif score >= 50:
            warning += 1
        else:
            critical += 1
        total_anomalies += health_state.open_anomaly_count
        total_clusters += health_state.active_cluster_count
        if score < worst_score:
            worst_score = score
            worst_service = service.name

    from datetime import datetime, timezone
    return FleetHealthSummary(
        total_services=total,
        healthy_count=healthy,
        warning_count=warning,
        critical_count=critical,
        total_open_anomalies=total_anomalies,
        total_active_clusters=total_clusters,
        most_at_risk_service=worst_service,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )
