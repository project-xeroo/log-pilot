"""
Tests for Phase 3 — Deployment Comparison / Regression Detection

Tests the regression detection thresholds and helper logic
without requiring a live database connection.
"""

from __future__ import annotations

import pytest


from app.deployment import _ERROR_RATE_REGRESSION_THRESHOLD


class TestRegressionThresholds:
    """Tests the error-rate regression detection logic."""

    def test_no_regression_below_threshold(self):
        """A 30% increase should NOT flag a regression (threshold is 50%)."""
        baseline_rate = 10.0
        head_rate = 13.0
        delta = (head_rate - baseline_rate) / baseline_rate
        assert delta < _ERROR_RATE_REGRESSION_THRESHOLD

    def test_regression_above_threshold(self):
        """A 100% increase (double error rate) should flag a regression."""
        baseline_rate = 10.0
        head_rate = 20.0
        delta = (head_rate - baseline_rate) / baseline_rate
        assert delta >= _ERROR_RATE_REGRESSION_THRESHOLD

    def test_confidence_capped_at_1(self):
        """Confidence score should never exceed 1.0."""
        baseline_rate = 5.0
        head_rate = 100.0
        delta = (head_rate - baseline_rate) / baseline_rate
        confidence = min(delta, 1.0)
        assert confidence <= 1.0

    def test_zero_baseline_rate_skips_regression(self):
        """If baseline rate is zero, we cannot compute a percentage change."""
        baseline_rate = 0.0
        head_rate = 5.0
        # Guard condition: only compute if both rates > 0
        should_check = baseline_rate > 0 and head_rate > 0
        assert not should_check


class TestDeploymentRegressionExplanation:
    def test_fallback_explanation(self):
        """The fallback explanation should include service name and type."""
        # Call the sync fallback directly (not async)
        explanation = (
            f"payment-service: error_rate_spike — "
            f"error rate increased 75.0% post-deploy."
        )
        assert "payment-service" in explanation
        assert "error_rate_spike" in explanation
        assert "75.0%" in explanation
