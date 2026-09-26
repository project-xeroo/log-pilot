"""
Baseline builder and deviation scorer.

The agent maintains a behavioural baseline for every service: the expected
error-count distribution per (severity, hour-of-day, day-of-week).

Deviation from that baseline — even at absolute values that seem low —
triggers risk elevation when the deviation profile matches historical
pre-failure patterns (PRD §4.1).

Storage: aggregate stats are computed on-the-fly from error_velocity_windows
using the last N days of history.  No extra table required.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import ErrorVelocityWindow


_BASELINE_DAYS = 28          # how far back to build the baseline
_MIN_SAMPLES = 3             # minimum windows needed to form a reliable baseline


async def _fetch_baseline_stats(
    db: AsyncSession,
    service_id: uuid.UUID,
    severity: str,
    hour_of_day: int,
    day_of_week: int,
) -> tuple[float, float]:
    """
    Return (mean, std_dev) of error_count for windows that match the same
    (service, severity, hour-of-day, day-of-week) over the past _BASELINE_DAYS.
    Returns (0.0, 1.0) if there is insufficient history.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_BASELINE_DAYS)

    stmt = (
        select(ErrorVelocityWindow.error_count)
        .where(
            ErrorVelocityWindow.service_id == service_id,
            ErrorVelocityWindow.severity == severity,
            ErrorVelocityWindow.window_start >= cutoff,
            extract("hour", ErrorVelocityWindow.window_start) == hour_of_day,
            extract("dow", ErrorVelocityWindow.window_start) == day_of_week,
        )
    )
    result = await db.execute(stmt)
    counts = [row[0] for row in result.all()]

    if len(counts) < _MIN_SAMPLES:
        return 0.0, 1.0   # not enough history; treat as zero deviation

    mean = sum(counts) / len(counts)
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    std_dev = math.sqrt(variance) or 1.0  # avoid division by zero
    return mean, std_dev


async def compute_baseline_score(
    db: AsyncSession,
    service_id: uuid.UUID,
    severity: str,
    current_count: int,
    evaluated_at: datetime,
) -> float:
    """
    Compare *current_count* against the historical baseline for the same
    (service, severity, hour, weekday) and return a 0-100 deviation score.

    A z-score of ≥3 (3 standard deviations) maps to 100.
    """
    hour = evaluated_at.hour
    dow = evaluated_at.weekday()   # Monday=0, Sunday=6

    mean, std_dev = await _fetch_baseline_stats(db, service_id, severity, hour, dow)

    z_score = abs(current_count - mean) / std_dev
    # Cap at 3σ → 100; linear below that
    score = min((z_score / 3.0) * 100.0, 100.0)
    return round(score, 2)
