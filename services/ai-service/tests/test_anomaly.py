"""
Tests for Phase 3 — Anomaly Detection

Tests the statistical helpers (z-score, baseline stats) and detector logic
without requiring a live database connection.
"""

from __future__ import annotations

import math
import pytest

from app.anomaly import _compute_stats, _z_score


class TestComputeStats:
    def test_mean(self):
        values = [2.0, 4.0, 6.0]
        mean, _ = _compute_stats(values)
        assert abs(mean - 4.0) < 1e-6

    def test_std_dev(self):
        values = [2.0, 4.0, 6.0]
        _, std = _compute_stats(values)
        # Population std for [2,4,6] = sqrt(((−2)²+0²+2²)/3) = sqrt(8/3) ≈ 1.633
        expected_std = math.sqrt(8 / 3)
        assert abs(std - expected_std) < 1e-4

    def test_insufficient_data_returns_defaults(self):
        mean, std = _compute_stats([1.0, 2.0])  # < 3 samples
        assert mean == 0.0
        assert std == 1.0

    def test_empty_returns_defaults(self):
        mean, std = _compute_stats([])
        assert mean == 0.0
        assert std == 1.0

    def test_all_same_value(self):
        """Zero variance should not cause divide-by-zero."""
        values = [5.0, 5.0, 5.0, 5.0]
        mean, std = _compute_stats(values)
        assert mean == 5.0
        assert std >= 1.0  # clamped to 1.0 to avoid division by zero


class TestZScore:
    def test_no_deviation(self):
        assert _z_score(5.0, 5.0, 1.0) == 0.0

    def test_one_sigma(self):
        assert abs(_z_score(6.0, 5.0, 1.0) - 1.0) < 1e-9

    def test_three_sigma(self):
        assert abs(_z_score(8.0, 5.0, 1.0) - 3.0) < 1e-9

    def test_below_mean(self):
        """z_score uses abs(), so below-mean deviations are positive."""
        assert abs(_z_score(2.0, 5.0, 1.0) - 3.0) < 1e-9

    def test_spike_exceeds_threshold(self):
        """A value 3.5σ above baseline should exceed the 3.0 default threshold."""
        baseline_mean = 100.0
        baseline_std = 10.0
        spike = 135.0  # 3.5 standard deviations above
        z = _z_score(spike, baseline_mean, baseline_std)
        threshold = 3.0
        assert z > threshold, f"z={z} should exceed threshold={threshold}"


class TestAnomalyDetectionLogic:
    """Higher-level logic tests that don't need a DB."""

    def test_spike_detector_threshold(self):
        """Verify the z-score threshold logic works with realistic values."""
        from app.anomaly import _compute_stats, _z_score
        from shared.config import get_settings
        settings = get_settings()

        # Build a baseline with low variance
        baseline = [50.0 + i % 5 for i in range(20)]
        mean, std = _compute_stats(baseline)

        # Normal value — should NOT trigger
        normal_val = mean + 1.5 * std
        assert _z_score(normal_val, mean, std) < settings.anomaly_zscore_threshold

        # Spike — should trigger
        spike_val = mean + settings.anomaly_zscore_threshold * std + 1
        assert _z_score(spike_val, mean, std) >= settings.anomaly_zscore_threshold
