"""
Anomaly Detection — Phase 3

PRD §5: Anomaly Detection Tool
  statistical baseline + ML outlier detection for spikes, new error types, service silences.
  Every anomaly is explained in natural language and appears in the Agent Feed unprompted.

Anomaly types:
  spike            — error count z-score exceeds threshold (statistical baseline deviation)
  new_error_type   — a new deduped error fingerprint appears for the first time
  service_silence  — service that normally produces logs goes quiet (no records)
  cluster_drift    — an existing cluster's centroid shifts significantly (embedding drift)

Anomalies are written to anomaly_events and published to Redis for the Agent Feed.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import (
    MonitoredService,
    AnomalyEvent,
    DeduplicatedError,
    ErrorCluster,
    ServiceHealthState,
)
from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Statistical helpers ───────────────────────────────────────────────────────

async def _fetch_baseline_error_counts(
    db: AsyncSession,
    service_id: uuid.UUID,
    *,
    lookback_days: int = 14,
    bucket_minutes: int = 60,
) -> list[float]:
    """
    Return hourly error counts over the past lookback_days (excluding the last hour).
    Used to compute the statistical baseline (mean + std).
    """
    stmt = text("""
        SELECT COUNT(*)::float AS cnt
        FROM log_records
        WHERE service_name = (
            SELECT name FROM monitored_services WHERE id = :service_id
        )
        AND severity IN ('ERROR', 'CRITICAL', 'FATAL')
        AND timestamp >= NOW() - INTERVAL '1 day' * :days
        AND timestamp < NOW() - INTERVAL '1 hour'
        GROUP BY date_trunc('hour', timestamp)
        ORDER BY date_trunc('hour', timestamp)
    """)
    result = await db.execute(stmt, {"service_id": str(service_id), "days": lookback_days})
    return [row.cnt for row in result.fetchall()]


async def _fetch_current_error_count(
    db: AsyncSession,
    service_id: uuid.UUID,
    *,
    window_minutes: int = 60,
) -> float:
    """Return the error count in the most recent window."""
    stmt = text("""
        SELECT COUNT(*)::float AS cnt
        FROM log_records
        WHERE service_name = (
            SELECT name FROM monitored_services WHERE id = :service_id
        )
        AND severity IN ('ERROR', 'CRITICAL', 'FATAL')
        AND timestamp >= NOW() - INTERVAL '1 minute' * :window
    """)
    result = await db.execute(stmt, {"service_id": str(service_id), "window": window_minutes})
    row = result.fetchone()
    return float(row.cnt) if row else 0.0


def _compute_stats(values: list[float]) -> tuple[float, float]:
    """Return (mean, std_dev) for a list of values. Returns (0, 1) if insufficient data."""
    if len(values) < 3:
        return 0.0, 1.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, math.sqrt(variance) or 1.0


def _z_score(value: float, mean: float, std: float) -> float:
    return abs(value - mean) / std


# ── LLM explanation generator ─────────────────────────────────────────────────

async def _generate_explanation(
    anomaly_type: str,
    service_name: str,
    context: dict[str, Any],
) -> str:
    """
    Generate a natural-language explanation for an anomaly.
    Falls back to a template-based explanation if AI is unavailable.
    """
    template_explanations = {
        "spike": (
            f"🔴 {service_name} is experiencing an error spike. "
            f"Current error rate is {context.get('observed_value', 0):.0f} errors/hour — "
            f"{context.get('z_score', 0):.1f}× above the normal baseline of "
            f"{context.get('baseline_mean', 0):.1f} ± {context.get('baseline_std', 0):.1f}."
        ),
        "new_error_type": (
            f"⚠️ {service_name} is producing a new type of error not seen before: "
            f"'{context.get('message', 'unknown error')[:120]}'. "
            f"This may indicate a newly introduced code path or dependency failure."
        ),
        "service_silence": (
            f"🔇 {service_name} has gone unexpectedly silent — no log records in the last "
            f"{context.get('silence_minutes', 60)} minutes. "
            f"The service may be down, unresponsive, or its log pipeline may be broken."
        ),
        "cluster_drift": (
            f"📈 Error cluster '{context.get('cluster_label', 'unknown')}' in {service_name} "
            f"is drifting. The error pattern is evolving toward new failure modes "
            f"(centroid shift: {context.get('drift_score', 0):.2f})."
        ),
    }
    fallback = template_explanations.get(
        anomaly_type,
        f"Anomaly detected in {service_name}: {anomaly_type}",
    )

    try:
        from app.providers import get_provider
        provider = get_provider()
        prompt = (
            f"Write a single clear sentence explaining this anomaly for an engineer's alert feed.\n"
            f"Service: {service_name}\n"
            f"Anomaly type: {anomaly_type}\n"
            f"Context: {json.dumps(context, default=str)}\n\n"
            f"Respond with ONLY the explanation sentence. No prefix, no labels."
        )
        resp = await provider.complete(prompt, max_tokens=80)
        return resp.content.strip()
    except Exception:
        return fallback


# ── Anomaly detection routines ────────────────────────────────────────────────

async def detect_spike(
    db: AsyncSession,
    service: MonitoredService,
) -> AnomalyEvent | None:
    """Detect statistical error-rate spike via z-score."""
    baseline_counts = await _fetch_baseline_error_counts(db, service.id)
    current_count = await _fetch_current_error_count(db, service.id)
    mean, std = _compute_stats(baseline_counts)
    z = _z_score(current_count, mean, std)

    if z < settings.anomaly_zscore_threshold:
        return None

    context = {
        "z_score": round(z, 2),
        "observed_value": current_count,
        "baseline_mean": round(mean, 2),
        "baseline_std": round(std, 2),
    }
    severity = "critical" if z > settings.anomaly_zscore_threshold * 2 else "warning"
    explanation = await _generate_explanation("spike", service.name, context)

    event = AnomalyEvent(
        id=uuid.uuid4(),
        service_id=service.id,
        anomaly_type="spike",
        explanation=explanation,
        z_score=round(z, 2),
        observed_value=current_count,
        baseline_mean=round(mean, 2),
        baseline_std=round(std, 2),
        severity=severity,
        detected_at=datetime.now(timezone.utc),
        is_resolved=False,
        context=context,
    )
    db.add(event)
    await db.flush()
    logger.info("Spike anomaly detected: service=%s z=%.2f", service.name, z)
    return event


async def detect_new_error_types(
    db: AsyncSession,
    service: MonitoredService,
    *,
    lookback_minutes: int = 60,
) -> list[AnomalyEvent]:
    """
    Detect brand-new deduped error fingerprints created in the last lookback_minutes
    that have never been seen before (occurrence_count == 1).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    stmt = (
        select(DeduplicatedError)
        .where(
            DeduplicatedError.service_id == service.id,
            DeduplicatedError.first_seen >= cutoff,
            DeduplicatedError.occurrence_count == 1,
        )
    )
    result = await db.execute(stmt)
    new_errors = result.scalars().all()

    events: list[AnomalyEvent] = []
    for err in new_errors:
        # Check we haven't already flagged this fingerprint
        existing = await db.execute(
            select(AnomalyEvent).where(
                AnomalyEvent.service_id == service.id,
                AnomalyEvent.anomaly_type == "new_error_type",
                AnomalyEvent.context["fingerprint"].astext == err.fingerprint,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue

        context = {
            "fingerprint": err.fingerprint,
            "message": err.canonical_message[:200],
            "severity": err.severity,
        }
        explanation = await _generate_explanation("new_error_type", service.name, context)

        event = AnomalyEvent(
            id=uuid.uuid4(),
            service_id=service.id,
            anomaly_type="new_error_type",
            explanation=explanation,
            severity="warning",
            detected_at=datetime.now(timezone.utc),
            is_resolved=False,
            context=context,
        )
        db.add(event)
        events.append(event)

    if events:
        await db.flush()
        logger.info("New error type anomalies: service=%s count=%d", service.name, len(events))
    return events


async def detect_service_silence(
    db: AsyncSession,
    service: MonitoredService,
    *,
    silence_threshold_minutes: int = 15,
    minimum_baseline_count: int = 10,
) -> AnomalyEvent | None:
    """
    Detect if an active service has gone silent (no log records in the threshold window).
    Only fires if the service has a meaningful historical baseline.
    """
    stmt = text("""
        SELECT COUNT(*) AS cnt
        FROM log_records
        WHERE service_name = :name
        AND timestamp >= NOW() - INTERVAL '1 minute' * :window
    """)
    result = await db.execute(stmt, {"name": service.name, "window": silence_threshold_minutes})
    recent_count = result.scalar() or 0

    if recent_count > 0:
        return None

    # Verify the service normally has logs (baseline)
    hist_stmt = text("""
        SELECT COUNT(*) AS cnt
        FROM log_records
        WHERE service_name = :name
        AND timestamp >= NOW() - INTERVAL '7 days'
        AND timestamp < NOW() - INTERVAL '1 minute' * :window
    """)
    hist_result = await db.execute(hist_stmt, {"name": service.name, "window": silence_threshold_minutes})
    hist_count = hist_result.scalar() or 0

    if hist_count < minimum_baseline_count:
        return None  # service never had meaningful logs

    # Check we haven't already flagged this silence
    existing = await db.execute(
        select(AnomalyEvent).where(
            AnomalyEvent.service_id == service.id,
            AnomalyEvent.anomaly_type == "service_silence",
            AnomalyEvent.is_resolved == False,  # noqa: E712
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        return None  # already open

    context = {"silence_minutes": silence_threshold_minutes}
    explanation = await _generate_explanation("service_silence", service.name, context)

    event = AnomalyEvent(
        id=uuid.uuid4(),
        service_id=service.id,
        anomaly_type="service_silence",
        explanation=explanation,
        severity="critical",
        detected_at=datetime.now(timezone.utc),
        is_resolved=False,
        context=context,
    )
    db.add(event)
    await db.flush()
    logger.warning("Service silence detected: service=%s", service.name)
    return event


# ── Agent Feed publisher ──────────────────────────────────────────────────────

def _publish_anomaly_to_agent_feed(
    service_name: str,
    anomaly_type: str,
    explanation: str,
    severity: str,
) -> None:
    """Publish natural-language anomaly explanation to Redis for the Agent Feed."""
    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.publish("logpilot:agent_feed", json.dumps({
            "type": "anomaly",
            "service": service_name,
            "anomaly_type": anomaly_type,
            "explanation": explanation,
            "severity": severity,
        }))
    except Exception as exc:
        logger.debug("Failed to publish anomaly to agent feed: %s", exc)


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_anomaly_detection(
    db: AsyncSession,
    service_id: uuid.UUID,
) -> dict:
    """
    Run all anomaly detectors for a service and publish results to the Agent Feed.
    Called by the analysis pipeline Celery task.
    """
    svc_result = await db.execute(
        select(MonitoredService).where(MonitoredService.id == service_id)
    )
    service = svc_result.scalar_one_or_none()
    if service is None:
        return {"error": "service not found"}

    detected: list[dict] = []

    spike = await detect_spike(db, service)
    if spike:
        detected.append({"type": "spike", "severity": spike.severity})
        _publish_anomaly_to_agent_feed(service.name, "spike", spike.explanation, spike.severity)

    new_errors = await detect_new_error_types(db, service)
    for ev in new_errors:
        detected.append({"type": "new_error_type", "severity": ev.severity})
        _publish_anomaly_to_agent_feed(service.name, "new_error_type", ev.explanation, ev.severity)

    silence = await detect_service_silence(db, service)
    if silence:
        detected.append({"type": "service_silence", "severity": silence.severity})
        _publish_anomaly_to_agent_feed(service.name, "service_silence", silence.explanation, silence.severity)

    await db.commit()

    logger.info("Anomaly detection: service=%s detected=%d", service.name, len(detected))
    return {"service": service.name, "anomalies_detected": len(detected), "details": detected}
