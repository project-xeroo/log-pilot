"""
Error velocity tracker.

Responsibilities:
- Record a new 60-second error-count window per (service, severity)
- Look back over the N most-recent windows and compute:
    first_derivative  = Δcount / Δt  (rate of change)
    second_derivative = ΔΔcount / Δt² (acceleration)
- Return a normalised velocity score 0-100 for the scoring layer
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import ErrorVelocityWindow, MonitoredService


# ── helpers ───────────────────────────────────────────────────────────────────

def _compute_derivatives(counts: list[int]) -> tuple[float, float]:
    """
    Given an ordered list of error counts (oldest → newest),
    return (first_derivative, second_derivative).
    Derivatives are expressed in counts-per-window (Δt = 1 window).
    """
    if len(counts) < 2:
        return 0.0, 0.0
    first_diffs = [counts[i + 1] - counts[i] for i in range(len(counts) - 1)]
    first_deriv = first_diffs[-1]  # most-recent Δ
    if len(first_diffs) < 2:
        return float(first_deriv), 0.0
    second_deriv = first_diffs[-1] - first_diffs[-2]
    return float(first_deriv), float(second_deriv)


def _normalise_velocity_score(
    count: int,
    first_deriv: float,
    second_deriv: float,
    *,
    count_cap: int = 500,
) -> float:
    """
    Convert raw velocity metrics into a 0-100 score component.

    Scoring rationale (PRD §4.1):
    - Exponential growth (positive second derivative) is heavily weighted
    - Absolute count contributes a baseline pressure
    - First derivative (sustained rise) contributes a mid-weight signal
    """
    # Clamp normalised inputs to [0, 1]
    count_norm = min(count / count_cap, 1.0)
    rate_norm = min(max(first_deriv, 0) / max(count_cap * 0.1, 1), 1.0)
    accel_norm = min(max(second_deriv, 0) / max(count_cap * 0.05, 1), 1.0)

    score = (count_norm * 30) + (rate_norm * 30) + (accel_norm * 40)
    return round(min(score * 100 / 100, 100.0), 2)


# ── public API ────────────────────────────────────────────────────────────────

async def record_window(
    db: AsyncSession,
    service_id: uuid.UUID,
    severity: str,
    error_count: int,
    window_start: datetime,
    window_end: datetime,
    lookback: int = 10,
) -> ErrorVelocityWindow:
    """
    Persist one velocity window and back-fill its derivatives by comparing
    against the previous *lookback* windows for the same (service, severity).
    """
    # Fetch recent windows to compute derivatives
    stmt = (
        select(ErrorVelocityWindow)
        .where(
            ErrorVelocityWindow.service_id == service_id,
            ErrorVelocityWindow.severity == severity,
        )
        .order_by(desc(ErrorVelocityWindow.window_start))
        .limit(lookback)
    )
    result = await db.execute(stmt)
    recent: Sequence[ErrorVelocityWindow] = result.scalars().all()

    # Oldest-first counts list + append the current window count
    counts = [w.error_count for w in reversed(recent)] + [error_count]
    first_deriv, second_deriv = _compute_derivatives(counts)

    window = ErrorVelocityWindow(
        id=uuid.uuid4(),
        service_id=service_id,
        severity=severity,
        error_count=error_count,
        window_start=window_start,
        window_end=window_end,
        first_derivative=first_deriv,
        second_derivative=second_deriv,
    )
    db.add(window)
    await db.flush()
    return window


async def compute_velocity_score(
    db: AsyncSession,
    service_id: uuid.UUID,
    severity: str = "ERROR",
    lookback: int = 10,
) -> float:
    """
    Read the N most-recent windows for (service, severity) and return
    a 0-100 velocity score for the risk-scoring layer.
    """
    stmt = (
        select(ErrorVelocityWindow)
        .where(
            ErrorVelocityWindow.service_id == service_id,
            ErrorVelocityWindow.severity == severity,
        )
        .order_by(desc(ErrorVelocityWindow.window_start))
        .limit(lookback)
    )
    result = await db.execute(stmt)
    windows: Sequence[ErrorVelocityWindow] = result.scalars().all()

    if not windows:
        return 0.0

    latest = windows[0]
    return _normalise_velocity_score(
        count=latest.error_count,
        first_deriv=latest.first_derivative or 0.0,
        second_deriv=latest.second_derivative or 0.0,
    )
