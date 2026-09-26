"""
Unit tests for the weighted risk scorer.
No DB required — pure function tests.
"""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.scoring.scorer import compute_risk_score, RiskResult


class TestComputeRiskScore:

    def test_normal_tier_below_warning(self):
        result = compute_risk_score(10.0, 20.0, 15.0)
        assert result.risk_tier == "normal"
        assert result.risk_score < 60.0

    def test_warning_tier(self):
        # velocity=70, similarity=65, baseline=55 → 70*0.3 + 65*0.4 + 55*0.3 = 21+26+16.5 = 63.5
        result = compute_risk_score(70.0, 65.0, 55.0)
        assert result.risk_tier == "warning"
        assert 60.0 <= result.risk_score < 80.0

    def test_critical_tier(self):
        # all at 90 → score = 90
        result = compute_risk_score(90.0, 90.0, 90.0)
        assert result.risk_tier == "critical"
        assert result.risk_score >= 80.0

    def test_exact_warning_boundary(self):
        # Arrange so composite == exactly 60.0
        # v*0.3 + s*0.4 + b*0.3 = 60  → all 60
        result = compute_risk_score(60.0, 60.0, 60.0)
        assert result.risk_tier == "warning"
        assert result.risk_score == 60.0

    def test_exact_critical_boundary(self):
        result = compute_risk_score(80.0, 80.0, 80.0)
        assert result.risk_tier == "critical"
        assert result.risk_score == 80.0

    def test_scores_clamped_to_100(self):
        result = compute_risk_score(200.0, 200.0, 200.0)
        assert result.risk_score == 100.0

    def test_zero_input(self):
        result = compute_risk_score(0.0, 0.0, 0.0)
        assert result.risk_score == 0.0
        assert result.risk_tier == "normal"

    def test_weight_mismatch_raises(self):
        with pytest.raises(AssertionError):
            compute_risk_score(50.0, 50.0, 50.0, weight_velocity=0.5, weight_similarity=0.5, weight_baseline=0.5)

    def test_result_is_frozen_dataclass(self):
        result = compute_risk_score(50.0, 50.0, 50.0)
        with pytest.raises(Exception):
            result.risk_score = 99.0  # type: ignore[misc]

    def test_custom_thresholds(self):
        result = compute_risk_score(50.0, 50.0, 50.0, warning_threshold=40.0, critical_threshold=90.0)
        assert result.risk_tier == "warning"

    def test_component_scores_preserved(self):
        result = compute_risk_score(30.0, 40.0, 50.0)
        assert result.velocity_score == 30.0
        assert result.similarity_score == 40.0
        assert result.baseline_score == 50.0
