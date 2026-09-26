"""
Analysis & Correlation Router — Phase 3

Endpoints:
  GET  /analysis/health                     — fleet health summary (all services)
  GET  /analysis/health/{service_id}        — single service health state
  GET  /analysis/dedup/{service_id}         — deduplicated errors for a service
  GET  /analysis/clusters/{service_id}      — error clusters for a service
  GET  /analysis/anomalies                  — list anomaly events
  GET  /analysis/anomalies/{anomaly_id}     — single anomaly
  POST /analysis/anomalies/{anomaly_id}/resolve  — mark anomaly resolved
  POST /analysis/rca/{service_id}           — trigger / return RCA for a service
  GET  /analysis/regressions               — list deployment regressions
  GET  /analysis/regressions/{service_id}  — regressions for one service
  POST /analysis/regressions/{regression_id}/acknowledge — SRE acknowledges regression
  POST /analysis/compare                   — manual deployment comparison trigger
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_db
from shared.models import (
    ServiceHealthState,
    MonitoredService,
    AnomalyEvent,
    ErrorCluster,
    DeduplicatedError,
    DeploymentRegression,
)
from app.auth.jwt_auth import AnyAuthenticated, SREOrAdmin, TokenPayload
from app.config import settings


async def _call_ai_service(path: str, payload: dict[str, Any], *, timeout: float) -> Any:
    """POST to the ai-service, which hosts the model-backed analysis tools."""
    try:
        async with httpx.AsyncClient(base_url=settings.ai_service_url, timeout=timeout) as client:
            resp = await client.post(path, json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {exc}") from exc
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=resp.json().get("detail", "Not found"))
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"AI service error: {resp.text[:200]}")
    return resp.json()

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ── Pydantic output schemas ───────────────────────────────────────────────────

class HealthStateOut(BaseModel):
    service_id: uuid.UUID
    service_name: str | None = None
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
    evaluated_at: datetime
    model_config = {"from_attributes": True}


class FleetHealthOut(BaseModel):
    total_services: int
    healthy_count: int
    warning_count: int
    critical_count: int
    total_open_anomalies: int
    total_active_clusters: int
    most_at_risk_service: str | None
    evaluated_at: str
    services: list[HealthStateOut]


class DedupErrorOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    fingerprint: str
    canonical_message: str
    severity: str
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime
    cluster_id: uuid.UUID | None
    model_config = {"from_attributes": True}


class ClusterOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    cluster_label: int
    auto_label: str | None
    confidence_score: float
    member_count: int
    is_active: bool
    first_seen: datetime
    last_seen: datetime
    model_config = {"from_attributes": True}


class AnomalyOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    cluster_id: uuid.UUID | None
    anomaly_type: str
    explanation: str
    z_score: float | None
    observed_value: float | None
    baseline_mean: float | None
    baseline_std: float | None
    severity: str
    detected_at: datetime
    resolved_at: datetime | None
    is_resolved: bool
    context: dict | None
    model_config = {"from_attributes": True}


class RegressionOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    baseline_version: str
    head_version: str
    regression_type: str
    explanation: str
    baseline_error_rate: float | None
    head_error_rate: float | None
    error_rate_delta: float | None
    cluster_id: uuid.UUID | None
    confidence: float | None
    detected_at: datetime
    acknowledged: bool
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    model_config = {"from_attributes": True}


class RCARequest(BaseModel):
    window_minutes: int = 30


class RCAOut(BaseModel):
    service_name: str
    window_start: str
    window_end: str
    root_cause_summary: str
    causal_chain: list[dict[str, Any]]
    affected_services: list[str]
    confidence_score: float
    ai_model: str
    duration_ms: float
    supporting_evidence: list[dict[str, Any]]


class CompareDeploymentsRequest(BaseModel):
    service_id: uuid.UUID
    baseline_version: str
    head_version: str
    baseline_deployed_at: datetime | None = None
    head_deployed_at: datetime | None = None
    window_hours: int = 2


class ResolveAnomalyRequest(BaseModel):
    resolved_by: str


class AcknowledgeRegressionRequest(BaseModel):
    acknowledged_by: str


# ── Fleet health summary ──────────────────────────────────────────────────────

@router.get("/health", response_model=FleetHealthOut, dependencies=[Depends(AnyAuthenticated)])
async def get_fleet_health(db: AsyncSession = Depends(get_db)):
    """
    Return the current health state for all active services.
    Backed by the service_health_states table (updated continuously by the analysis pipeline).
    Performance target: < 3 seconds.
    """
    stmt = (
        select(ServiceHealthState, MonitoredService)
        .join(MonitoredService, MonitoredService.id == ServiceHealthState.service_id)
        .where(MonitoredService.is_active == True)  # noqa: E712
        .order_by(ServiceHealthState.health_score.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    services_out = []
    healthy = warning = critical = 0
    total_anomalies = total_clusters = 0
    worst_service = None
    worst_score = 101.0

    for hs, svc in rows:
        out = HealthStateOut(
            service_id=hs.service_id,
            service_name=svc.name,
            health_score=hs.health_score,
            baseline_error_rate=hs.baseline_error_rate,
            current_error_rate=hs.current_error_rate,
            baseline_deviation_z=hs.baseline_deviation_z,
            active_cluster_count=hs.active_cluster_count,
            total_deduped_error_count=hs.total_deduped_error_count,
            open_anomaly_count=hs.open_anomaly_count,
            top_cluster_label=hs.top_cluster_label,
            latest_risk_tier=hs.latest_risk_tier,
            latest_risk_score=hs.latest_risk_score,
            evaluated_at=hs.evaluated_at,
        )
        services_out.append(out)
        total_anomalies += hs.open_anomaly_count
        total_clusters += hs.active_cluster_count
        if hs.health_score >= 80:
            healthy += 1
        elif hs.health_score >= 50:
            warning += 1
        else:
            critical += 1
        if hs.health_score < worst_score:
            worst_score = hs.health_score
            worst_service = svc.name

    return FleetHealthOut(
        total_services=len(rows),
        healthy_count=healthy,
        warning_count=warning,
        critical_count=critical,
        total_open_anomalies=total_anomalies,
        total_active_clusters=total_clusters,
        most_at_risk_service=worst_service,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        services=services_out,
    )


@router.get("/health/{service_id}", response_model=HealthStateOut, dependencies=[Depends(AnyAuthenticated)])
async def get_service_health(service_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return the current health state for a single service."""
    result = await db.execute(
        select(ServiceHealthState).where(ServiceHealthState.service_id == service_id).limit(1)
    )
    hs = result.scalar_one_or_none()
    if hs is None:
        raise HTTPException(status_code=404, detail="No health state found for this service")
    svc_result = await db.execute(select(MonitoredService).where(MonitoredService.id == service_id))
    svc = svc_result.scalar_one_or_none()
    return HealthStateOut(
        service_id=hs.service_id,
        service_name=svc.name if svc else None,
        health_score=hs.health_score,
        baseline_error_rate=hs.baseline_error_rate,
        current_error_rate=hs.current_error_rate,
        baseline_deviation_z=hs.baseline_deviation_z,
        active_cluster_count=hs.active_cluster_count,
        total_deduped_error_count=hs.total_deduped_error_count,
        open_anomaly_count=hs.open_anomaly_count,
        top_cluster_label=hs.top_cluster_label,
        latest_risk_tier=hs.latest_risk_tier,
        latest_risk_score=hs.latest_risk_score,
        evaluated_at=hs.evaluated_at,
    )


# ── Deduplicated errors ───────────────────────────────────────────────────────

@router.get("/dedup/{service_id}", response_model=list[DedupErrorOut], dependencies=[Depends(AnyAuthenticated)])
async def list_dedup_errors(
    service_id: uuid.UUID,
    limit: int = Query(50, le=200),
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return deduplicated errors for a service, ordered by occurrence count desc."""
    stmt = (
        select(DeduplicatedError)
        .where(DeduplicatedError.service_id == service_id)
        .order_by(DeduplicatedError.occurrence_count.desc())
    )
    if severity:
        stmt = stmt.where(DeduplicatedError.severity == severity.upper())
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Error clusters ────────────────────────────────────────────────────────────

@router.get("/clusters/{service_id}", response_model=list[ClusterOut], dependencies=[Depends(AnyAuthenticated)])
async def list_clusters(
    service_id: uuid.UUID,
    active_only: bool = True,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return error clusters for a service, ordered by member count desc."""
    stmt = (
        select(ErrorCluster)
        .where(ErrorCluster.service_id == service_id)
        .order_by(ErrorCluster.member_count.desc())
    )
    if active_only:
        stmt = stmt.where(ErrorCluster.is_active == True)  # noqa: E712
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Anomalies ─────────────────────────────────────────────────────────────────

@router.get("/anomalies", response_model=list[AnomalyOut], dependencies=[Depends(AnyAuthenticated)])
async def list_anomalies(
    service_id: uuid.UUID | None = None,
    resolved: bool = False,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return anomaly events. Defaults to unresolved."""
    stmt = (
        select(AnomalyEvent)
        .where(AnomalyEvent.is_resolved == resolved)
        .order_by(desc(AnomalyEvent.detected_at))
    )
    if service_id:
        stmt = stmt.where(AnomalyEvent.service_id == service_id)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/anomalies/{anomaly_id}", response_model=AnomalyOut, dependencies=[Depends(AnyAuthenticated)])
async def get_anomaly(anomaly_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return anomaly


@router.post("/anomalies/{anomaly_id}/resolve", response_model=AnomalyOut)
async def resolve_anomaly(
    anomaly_id: uuid.UUID,
    body: ResolveAnomalyRequest,
    user: TokenPayload = Depends(SREOrAdmin),
    db: AsyncSession = Depends(get_db),
):
    """Mark an anomaly as resolved."""
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    if anomaly.is_resolved:
        raise HTTPException(status_code=409, detail="Anomaly is already resolved")
    anomaly.is_resolved = True
    anomaly.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(anomaly)
    return anomaly


# ── Root Cause Analysis ───────────────────────────────────────────────────────

@router.post("/rca/{service_id}", response_model=RCAOut)
async def run_rca(
    service_id: uuid.UUID,
    body: RCARequest,
    user: TokenPayload = Depends(AnyAuthenticated),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a root cause analysis for a service.
    Runs temporal correlation + service dependency inference + deep reasoning model.
    Performance target: < 15 seconds.
    """
    data = await _call_ai_service(f"/analysis/rca/{service_id}", body.model_dump(mode="json"), timeout=30.0)
    return RCAOut(**data)


# ── Deployment regressions ────────────────────────────────────────────────────

@router.get("/regressions", response_model=list[RegressionOut], dependencies=[Depends(AnyAuthenticated)])
async def list_regressions(
    service_id: uuid.UUID | None = None,
    acknowledged: bool = False,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List deployment regressions."""
    stmt = (
        select(DeploymentRegression)
        .where(DeploymentRegression.acknowledged == acknowledged)
        .order_by(desc(DeploymentRegression.detected_at))
    )
    if service_id:
        stmt = stmt.where(DeploymentRegression.service_id == service_id)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/regressions/{service_id}/service", response_model=list[RegressionOut], dependencies=[Depends(AnyAuthenticated)])
async def list_regressions_for_service(
    service_id: uuid.UUID,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List deployment regressions for a specific service."""
    result = await db.execute(
        select(DeploymentRegression)
        .where(DeploymentRegression.service_id == service_id)
        .order_by(desc(DeploymentRegression.detected_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/regressions/{regression_id}/acknowledge", response_model=RegressionOut)
async def acknowledge_regression(
    regression_id: uuid.UUID,
    body: AcknowledgeRegressionRequest,
    user: TokenPayload = Depends(SREOrAdmin),
    db: AsyncSession = Depends(get_db),
):
    """SRE acknowledges a detected regression."""
    result = await db.execute(select(DeploymentRegression).where(DeploymentRegression.id == regression_id))
    reg = result.scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Regression not found")
    if reg.acknowledged:
        raise HTTPException(status_code=409, detail="Regression already acknowledged")
    reg.acknowledged = True
    reg.acknowledged_by = body.acknowledged_by
    reg.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(reg)
    return reg


@router.post("/compare", response_model=list[RegressionOut])
async def compare_deployments(
    body: CompareDeploymentsRequest,
    user: TokenPayload = Depends(SREOrAdmin),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a deployment comparison between two versions.
    Returns any detected regressions.
    """
    data = await _call_ai_service("/analysis/compare", body.model_dump(mode="json"), timeout=60.0)
    ids = [uuid.UUID(i) for i in data.get("regression_ids", [])]
    if not ids:
        return []
    result = await db.execute(select(DeploymentRegression).where(DeploymentRegression.id.in_(ids)))
    return result.scalars().all()
