"""
Forecasting loop — the core Celery beat task (PRD §4.2).

One task per service runs every *loop_interval_seconds* (default 60s).
The full cycle:
  1. Fetch the most-recent error-velocity window for the service
  2. Compute velocity score (tracker)
  3. Compute baseline deviation score (builder)
  4. Fetch current embedding → compute leading-indicator similarity (matcher)
  5. Compute weighted risk score (scorer)
  6. Persist a RiskSnapshot
  7. If score ≥ warning threshold → create PreIncidentAlert + (if critical) trigger pre-mortem
  8. Publish alert to notification service via Redis pub/sub
  9. Graceful degradation: if AI call fails, fall back to threshold-based alert

Autonomy enforcement:
  - "proactive_forecasting" alert creation is subject to the autonomy_policy table
  - "pre_mortem_report" drafting checks its own policy row
  - Any action outside granted tier is written as "propose" and queued for human approval
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import AsyncSessionLocal, get_settings
from shared.models import (
    MonitoredService,
    RiskSnapshot,
    PreIncidentAlert,
)
from sqlalchemy import select

from app.velocity import compute_velocity_score
from app.baseline import compute_baseline_score
from app.drift import compute_drift_score
from app.indicators import find_similar_incidents
from app.scoring import compute_risk_score
from app.loop.autonomy import resolve_autonomy_tier, record_action
from shared.utils.feed import publish_feed_entry, record_feed_entry

logger = logging.getLogger(__name__)
settings = get_settings()


# ── helpers ───────────────────────────────────────────────────────────────────

async def _get_latest_error_count(db: AsyncSession, service_id: uuid.UUID) -> tuple[int, datetime]:
    """Return (latest error count, window_start) from the most-recent velocity window."""
    from shared.models import ErrorVelocityWindow
    from sqlalchemy import desc

    stmt = (
        select(ErrorVelocityWindow)
        .where(ErrorVelocityWindow.service_id == service_id, ErrorVelocityWindow.severity == "ERROR")
        .order_by(desc(ErrorVelocityWindow.window_start))
        .limit(1)
    )
    result = await db.execute(stmt)
    window = result.scalar_one_or_none()
    if window:
        return window.error_count, window.window_start
    return 0, datetime.now(timezone.utc)


async def _get_latest_embedding(db: AsyncSession, service_id: uuid.UUID) -> list[float] | None:
    """Return the most-recent embedding vector for a service (for similarity search)."""
    from sqlalchemy import text
    stmt = text("""
        SELECT embedding FROM leading_indicator_embeddings
        WHERE service_id = :service_id
        ORDER BY created_at DESC LIMIT 1
    """)
    result = await db.execute(stmt, {"service_id": str(service_id)})
    row = result.fetchone()
    if row:
        return list(row[0])
    return None


async def _build_threshold_explanation(service_name: str, risk_score: float, tier: str) -> str:
    """Fallback explanation used when AI is unavailable (graceful degradation)."""
    return (
        f"[Threshold-based alert — AI inference unavailable] "
        f"Service '{service_name}' has crossed the {tier} threshold "
        f"with a raw risk score of {risk_score:.1f}. "
        f"Manual investigation is recommended."
    )


async def _run_cycle(service: MonitoredService, db: AsyncSession) -> None:
    """Execute one full forecasting cycle for a single service."""
    service_id: uuid.UUID = service.id
    now = datetime.now(timezone.utc)

    # ── 1-3. Sub-scores ───────────────────────────────────────────────────────
    error_count, window_start = await _get_latest_error_count(db, service_id)

    velocity_score = await compute_velocity_score(db, service_id, severity="ERROR")
    baseline_score = await compute_baseline_score(db, service_id, "ERROR", error_count, now)
    drift_score = await compute_drift_score(db, service_id)

    # ── 4. Similarity / leading-indicator matching ────────────────────────────
    ai_assisted = True
    indicator_result: dict = {
        "similarity_score": drift_score,  # fallback: use drift as similarity proxy
        "similar_past_event_ids": [],
        "matched_pattern": None,
        "confidence": None,
    }
    try:
        embedding = await _get_latest_embedding(db, service_id)
        if embedding:
            indicator_result = await find_similar_incidents(db, service_id, embedding)
    except Exception as exc:
        logger.warning("AI similarity search failed for service %s: %s — using fallback", service.name, exc)
        ai_assisted = False

    similarity_score: float = indicator_result["similarity_score"]

    # ── 5. Weighted risk score ────────────────────────────────────────────────
    risk = compute_risk_score(
        velocity_score=velocity_score,
        similarity_score=similarity_score,
        baseline_score=baseline_score,
        weight_velocity=settings.weight_velocity,
        weight_similarity=settings.weight_similarity,
        weight_baseline=settings.weight_baseline,
        warning_threshold=settings.forecasting_warning_threshold,
        critical_threshold=settings.forecasting_critical_threshold,
    )

    # ── 6. Persist RiskSnapshot ───────────────────────────────────────────────
    snapshot = RiskSnapshot(
        id=uuid.uuid4(),
        service_id=service_id,
        evaluated_at=now,
        velocity_score=risk.velocity_score,
        similarity_score=risk.similarity_score,
        baseline_score=risk.baseline_score,
        risk_score=risk.risk_score,
        risk_tier=risk.risk_tier,
        ai_assisted=ai_assisted,
    )
    db.add(snapshot)
    await db.flush()

    if risk.risk_tier == "normal":
        await db.commit()
        return  # nothing to alert

    # ── 7. Create PreIncidentAlert ────────────────────────────────────────────
    tier = await resolve_autonomy_tier(
        db, tool_name="proactive_forecasting", environment=service.environment
    )

    if ai_assisted:
        explanation = (
            f"Service '{service.name}' is showing elevated risk "
            f"(score {risk.risk_score:.1f}, tier: {risk.risk_tier}). "
            f"Matched pattern: {indicator_result['matched_pattern'] or 'unknown'}. "
            f"Velocity signal is {velocity_score:.1f}/100, "
            f"baseline deviation is {baseline_score:.1f}/100."
        )
    else:
        explanation = await _build_threshold_explanation(service.name, risk.risk_score, risk.risk_tier)

    # Automatically downgrade to propose if outside granted tier
    effective_tier = tier if tier in ("observe", "propose", "auto") else "propose"

    alert = PreIncidentAlert(
        id=uuid.uuid4(),
        service_id=service_id,
        snapshot_id=snapshot.id,
        risk_score=risk.risk_score,
        risk_tier=risk.risk_tier,
        explanation=explanation,
        matched_pattern=indicator_result.get("matched_pattern"),
        confidence=indicator_result.get("confidence"),
        similar_past_event_ids=indicator_result.get("similar_past_event_ids", []),
        recommended_actions=_default_recommended_actions(risk.risk_tier),
        status="open",
        alerted_at=now,
    )
    db.add(alert)
    await db.flush()

    # Audit the alert creation
    await record_action(
        db,
        tool_name="proactive_forecasting",
        service_id=service_id,
        trigger="scheduled_loop",
        confidence=indicator_result.get("confidence"),
        autonomy_tier=effective_tier,
        description=f"Pre-incident alert created for {service.name} at risk score {risk.risk_score:.1f}",
    )

    # ── 8. Trigger pre-mortem if critical ─────────────────────────────────────
    if risk.risk_tier == "critical":
        from app.loop.premortem_trigger import maybe_draft_premortem
        await maybe_draft_premortem(db, service=service, alert=alert, ai_assisted=ai_assisted)

    # Surface the alert in the Agent Feed history (savepoint: never block the alert)
    feed_entry = None
    try:
        async with db.begin_nested():
            feed_entry = await record_feed_entry(
                db,
                entry_type="alert_fired",
                title=f"{service.name}: {risk.risk_tier} failure risk ({risk.risk_score:.0f}/100)",
                body=explanation,
                service_name=service.name,
                severity=risk.risk_tier,
                risk_score=risk.risk_score,
                metadata={"alert_id": str(alert.id)},
            )
    except Exception as exc:
        logger.warning("Failed to record alert in agent feed: %s", exc)

    await db.commit()

    # ── 9. Publish to notification service + live Agent Feed ─────────────────
    _publish_alert(alert_id=str(alert.id), service_name=service.name, risk_tier=risk.risk_tier)
    if feed_entry:
        publish_feed_entry(settings.redis_url, feed_entry)


def _default_recommended_actions(tier: str) -> list[dict]:
    """Return a default set of propose-only recommended actions for the alert."""
    if tier == "critical":
        return [
            {"priority": 1, "action": "Page on-call SRE immediately"},
            {"priority": 2, "action": "Review error logs for the last 15 minutes"},
            {"priority": 3, "action": "Check recent deployments for this service"},
            {"priority": 4, "action": "Prepare rollback plan"},
        ]
    return [
        {"priority": 1, "action": "Monitor error rate closely for the next 10 minutes"},
        {"priority": 2, "action": "Review error logs for the last 15 minutes"},
        {"priority": 3, "action": "Check recent deployments for this service"},
    ]


def _publish_alert(alert_id: str, service_name: str, risk_tier: str) -> None:
    """Push alert metadata to the notification service via Redis pub/sub."""
    try:
        import redis
        from shared.config import get_settings as _gs
        r = redis.from_url(_gs().redis_url)
        import json
        r.publish("logpilot:alerts", json.dumps({
            "alert_id": alert_id,
            "service_name": service_name,
            "risk_tier": risk_tier,
        }))
    except Exception as exc:
        logger.warning("Failed to publish alert to Redis: %s", exc)


# ── Celery task entry point ───────────────────────────────────────────────────

@shared_task(
    name="forecasting.run_cycle_for_service",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def run_cycle_for_service(self, service_id: str) -> dict:
    """Celery task: run one forecasting cycle for the given service."""
    async def _inner():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MonitoredService).where(MonitoredService.id == uuid.UUID(service_id))
            )
            service = result.scalar_one_or_none()
            if service is None or not service.is_active:
                return {"status": "skipped", "reason": "service not found or inactive"}
            await _run_cycle(service, db)
            return {"status": "ok", "service": service.name}

    try:
        return asyncio.get_event_loop().run_until_complete(_inner())
    except Exception as exc:
        logger.error("Forecasting cycle failed for service %s: %s", service_id, exc)
        raise self.retry(exc=exc)
