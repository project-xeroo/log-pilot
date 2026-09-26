from __future__ import annotations

"""Feedback loop — updates ForecastWeight rows after each IncidentOutcome is logged.

Algorithm (online learning, no external ML library required):
  - true_positive  → increase weight (signal was correct)
  - false_positive → decrease weight (signal was noise)
  - false_negative → decrease weight for indicators that should have fired
  - true_negative  → no change (no information gain)

Weight update rule:
  new_weight = clamp(old_weight + lr * delta, weight_min, weight_max)
  where delta = +1 for TP, -1 for FP, -0.5 for FN (partial penalty)

Running precision/recall are maintained for observability.
"""

import logging
from typing import Sequence

from sqlalchemy.orm import Session

from app.config import settings
from shared.models import ForecastWeight, OutcomeVerdict

logger = logging.getLogger("forecasting.loop")

_LR = settings.weight_learning_rate
_MIN = settings.weight_min
_MAX = settings.weight_max


def _clamp(value: float) -> float:
    return max(_MIN, min(_MAX, value))


def _get_or_create_weight(session: Session, indicator: str) -> ForecastWeight:
    fw = session.query(ForecastWeight).filter_by(indicator_name=indicator).first()
    if fw is None:
        fw = ForecastWeight(indicator_name=indicator, weight=1.0)
        session.add(fw)
        session.flush()
    return fw


def apply_outcome_feedback(
    session: Session,
    verdict: OutcomeVerdict,
    fired_indicators: Sequence[str],
    forecast_accurate: bool | None,
) -> list[dict]:
    """Update indicator weights based on a single outcome verdict.

    Returns a list of {indicator, old_weight, new_weight, delta} for logging.
    """
    updates: list[dict] = []

    if verdict == OutcomeVerdict.true_negative:
        return updates  # No information to extract

    if verdict == OutcomeVerdict.true_positive:
        delta = +1.0
    elif verdict == OutcomeVerdict.false_positive:
        delta = -1.0
    else:  # false_negative
        delta = -0.5

    for indicator in fired_indicators:
        fw = _get_or_create_weight(session, indicator)
        old = fw.weight
        fw.weight = _clamp(old + _LR * delta)
        fw.total_fired += 1

        if verdict == OutcomeVerdict.true_positive:
            fw.true_positive_count += 1
        elif verdict == OutcomeVerdict.false_positive:
            fw.false_positive_count += 1
        elif verdict == OutcomeVerdict.false_negative:
            fw.false_negative_count += 1

        # Recompute precision and recall
        tp = fw.true_positive_count
        fp = fw.false_positive_count
        fn = fw.false_negative_count
        fw.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        fw.recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        updates.append(
            {
                "indicator": indicator,
                "old_weight": round(old, 4),
                "new_weight": round(fw.weight, 4),
                "delta": round(_LR * delta, 4),
                "precision": round(fw.precision, 4),
                "recall": round(fw.recall, 4),
            }
        )
        logger.info(
            "Weight update: %s  %.4f → %.4f  (verdict=%s)",
            indicator, old, fw.weight, verdict,
        )

    session.flush()
    return updates
