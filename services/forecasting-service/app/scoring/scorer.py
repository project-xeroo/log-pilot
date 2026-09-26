"""
Weighted risk scorer (PRD §4.2).

Combines the three sub-scores into a single 0-100 composite:
  velocity_score   × 0.30  (error velocity + acceleration)
  similarity_score × 0.40  (leading indicator / vector similarity)
  baseline_score   × 0.30  (deviation from historical baseline)

Returns the composite score and the resolved risk tier:
  normal   (< warning_threshold)
  warning  (≥ warning_threshold, < critical_threshold)
  critical (≥ critical_threshold)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskResult:
    velocity_score: float
    similarity_score: float
    baseline_score: float
    risk_score: float
    risk_tier: str   # "normal" | "warning" | "critical"


def compute_risk_score(
    velocity_score: float,
    similarity_score: float,
    baseline_score: float,
    *,
    weight_velocity: float = 0.30,
    weight_similarity: float = 0.40,
    weight_baseline: float = 0.30,
    warning_threshold: float = 60.0,
    critical_threshold: float = 80.0,
) -> RiskResult:
    """
    Combine sub-scores into the weighted composite and assign a risk tier.

    All inputs are expected in the 0-100 range; weights must sum to 1.0.
    """
    assert abs(weight_velocity + weight_similarity + weight_baseline - 1.0) < 1e-6, \
        "Weights must sum to 1.0"

    risk_score = (
        velocity_score * weight_velocity
        + similarity_score * weight_similarity
        + baseline_score * weight_baseline
    )
    risk_score = round(min(max(risk_score, 0.0), 100.0), 2)

    if risk_score >= critical_threshold:
        tier = "critical"
    elif risk_score >= warning_threshold:
        tier = "warning"
    else:
        tier = "normal"

    return RiskResult(
        velocity_score=round(velocity_score, 2),
        similarity_score=round(similarity_score, 2),
        baseline_score=round(baseline_score, 2),
        risk_score=risk_score,
        risk_tier=tier,
    )
