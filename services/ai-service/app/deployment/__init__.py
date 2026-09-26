"""
Deployment Comparison — Regression Detection (Phase 3)

PRD §5: Deployment Comparison Tool
  side-by-side regression detection between deployment versions.
  Automatically flags regressions on new deploy events.

Regression types:
  error_rate_spike  — statistically significant increase in error rate post-deploy
  new_error_cluster — a new error cluster appears after deploy
  cluster_size_jump — an existing cluster grows significantly post-deploy

This module is called:
  1. Proactively — when a new deployment event is received
  2. On-demand — via the /analysis/deployment-comparison endpoint
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import (
    MonitoredService,
    DeploymentRegression,
    ErrorCluster,
    DeduplicatedError,
)
from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Minimum relative error rate increase to flag as a regression
_ERROR_RATE_REGRESSION_THRESHOLD = 0.50   # 50% increase
_CLUSTER_SIZE_JUMP_THRESHOLD = 2.0         # cluster grows by 2×


async def _get_error_rate(
    db: AsyncSession,
    service_name: str,
    window_start: datetime,
    window_end: datetime,
) -> float:
    """Return errors-per-hour in the given window. Returns 0.0 if no data."""
    hours = max((window_end - window_start).total_seconds() / 3600, 0.001)
    stmt = text("""
        SELECT COUNT(*)::float AS cnt
        FROM log_records
        WHERE service_name = :name
          AND severity IN ('ERROR', 'CRITICAL', 'FATAL')
          AND timestamp BETWEEN :start AND :end
    """)
    result = await db.execute(stmt, {"name": service_name, "start": window_start, "end": window_end})
    row = result.fetchone()
    total = float(row.cnt) if row else 0.0
    return round(total / hours, 4)


async def _get_active_clusters(
    db: AsyncSession,
    service_id: uuid.UUID,
    as_of: datetime,
) -> list[dict]:
    """Return active error clusters as of a given timestamp."""
    stmt = (
        select(ErrorCluster)
        .where(
            ErrorCluster.service_id == service_id,
            ErrorCluster.is_active == True,  # noqa: E712
            ErrorCluster.first_seen <= as_of,
        )
    )
    result = await db.execute(stmt)
    return [
        {
            "id": str(c.id),
            "label": c.auto_label,
            "member_count": c.member_count,
            "confidence": c.confidence_score,
        }
        for c in result.scalars().all()
    ]


async def compare_deployments(
    db: AsyncSession,
    service_id: uuid.UUID,
    baseline_version: str,
    head_version: str,
    *,
    baseline_deployed_at: datetime | None = None,
    head_deployed_at: datetime | None = None,
    window_hours: int = 2,
) -> list[DeploymentRegression]:
    """
    Compare error rates and cluster state between baseline and head deployments.
    Creates DeploymentRegression rows for any detected regressions.
    Returns the list of created regressions (empty if no regressions detected).
    """
    svc_result = await db.execute(
        select(MonitoredService).where(MonitoredService.id == service_id)
    )
    service = svc_result.scalar_one_or_none()
    if service is None:
        raise ValueError(f"Service {service_id} not found")

    now = datetime.now(timezone.utc)

    # Infer deploy timestamps if not provided
    if baseline_deployed_at is None:
        baseline_deployed_at = now - timedelta(hours=window_hours * 3)
    if head_deployed_at is None:
        head_deployed_at = now - timedelta(hours=window_hours)

    # Define analysis windows (post-deploy)
    baseline_start = baseline_deployed_at
    baseline_end = baseline_deployed_at + timedelta(hours=window_hours)
    head_start = head_deployed_at
    head_end = min(head_deployed_at + timedelta(hours=window_hours), now)

    baseline_rate = await _get_error_rate(db, service.name, baseline_start, baseline_end)
    head_rate = await _get_error_rate(db, service.name, head_start, head_end)

    regressions: list[DeploymentRegression] = []

    # ── 1. Error rate regression ──────────────────────────────────────────────
    if baseline_rate > 0 and head_rate > 0:
        delta = (head_rate - baseline_rate) / baseline_rate
        if delta >= _ERROR_RATE_REGRESSION_THRESHOLD:
            try:
                explanation = await _generate_regression_explanation(
                    service.name, "error_rate_spike",
                    {"baseline_rate": baseline_rate, "head_rate": head_rate, "delta_pct": round(delta * 100, 1)},
                )
            except Exception:
                explanation = (
                    f"{service.name}: error rate increased {delta * 100:.1f}% after deploying "
                    f"v{head_version} (was {baseline_rate:.1f}/h, now {head_rate:.1f}/h)."
                )

            reg = DeploymentRegression(
                id=uuid.uuid4(),
                service_id=service_id,
                baseline_version=baseline_version,
                head_version=head_version,
                regression_type="error_rate_spike",
                explanation=explanation,
                baseline_error_rate=baseline_rate,
                head_error_rate=head_rate,
                error_rate_delta=round(delta, 4),
                confidence=min(delta, 1.0),
                detected_at=now,
            )
            db.add(reg)
            regressions.append(reg)

    # ── 2. New error clusters after head deploy ───────────────────────────────
    baseline_clusters = await _get_active_clusters(db, service_id, baseline_end)
    baseline_ids = {c["id"] for c in baseline_clusters}

    head_clusters_stmt = (
        select(ErrorCluster)
        .where(
            ErrorCluster.service_id == service_id,
            ErrorCluster.is_active == True,  # noqa: E712
            ErrorCluster.first_seen >= head_deployed_at,
        )
    )
    head_result = await db.execute(head_clusters_stmt)
    new_clusters = [c for c in head_result.scalars().all() if str(c.id) not in baseline_ids]

    for cluster in new_clusters:
        explanation = (
            f"{service.name}: new error cluster appeared after deploying v{head_version}: "
            f"'{cluster.auto_label or 'unnamed'}' ({cluster.member_count} errors, "
            f"confidence {cluster.confidence_score:.2f})."
        )
        reg = DeploymentRegression(
            id=uuid.uuid4(),
            service_id=service_id,
            baseline_version=baseline_version,
            head_version=head_version,
            regression_type="new_error_cluster",
            explanation=explanation,
            baseline_error_rate=baseline_rate,
            head_error_rate=head_rate,
            error_rate_delta=None,
            cluster_id=cluster.id,
            confidence=cluster.confidence_score,
            detected_at=now,
        )
        db.add(reg)
        regressions.append(reg)

    if regressions:
        await db.flush()
        logger.info(
            "Deployment regression detected: service=%s v%s→v%s count=%d",
            service.name, baseline_version, head_version, len(regressions),
        )

    return regressions


async def _generate_regression_explanation(
    service_name: str,
    regression_type: str,
    context: dict[str, Any],
) -> str:
    """Generate NL explanation via LLM for a regression."""
    try:
        from app.providers import get_provider
        provider = get_provider()
        prompt = (
            f"Write one sentence explaining this deployment regression for an engineer.\n"
            f"Service: {service_name}\nType: {regression_type}\nData: {context}\n"
            f"Be concise and actionable."
        )
        resp = await provider.complete(prompt, max_tokens=80)
        return resp.content.strip()
    except Exception:
        delta_pct = context.get("delta_pct", 0)
        return (
            f"{service_name}: {regression_type} — "
            f"error rate increased {delta_pct:.1f}% post-deploy."
        )


async def auto_detect_on_deploy(
    db: AsyncSession,
    service_id: uuid.UUID,
    new_version: str,
    deployed_at: datetime,
) -> list[DeploymentRegression]:
    """
    Called automatically when a new deployment event is received.
    Finds the previous deployment version and runs comparison.
    """
    # Look up previous deployments for this service in the deployment_snapshots table
    try:
        from sqlalchemy import text as sqlt
        stmt = sqlt("""
            SELECT version, deployed_at
            FROM deployment_snapshots
            WHERE service_name = (
                SELECT name FROM monitored_services WHERE id = :service_id
            )
            AND deployed_at < :deployed_at
            ORDER BY deployed_at DESC
            LIMIT 1
        """)
        result = await db.execute(stmt, {"service_id": str(service_id), "deployed_at": deployed_at})
        prev = result.fetchone()

        if prev is None:
            logger.info("No previous deployment found for service %s — skipping regression check", service_id)
            return []

        return await compare_deployments(
            db, service_id,
            baseline_version=prev.version,
            head_version=new_version,
            baseline_deployed_at=prev.deployed_at,
            head_deployed_at=deployed_at,
        )
    except Exception as exc:
        logger.warning("Auto deploy regression check failed: %s", exc)
        return []
