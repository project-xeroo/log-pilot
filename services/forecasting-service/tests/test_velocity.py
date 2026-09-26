"""
Unit tests for velocity derivative calculation.
Tests the pure helper functions — no DB required.
"""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.velocity.tracker import (
    _compute_derivatives,
    _normalise_velocity_score,
)


class TestComputeDerivatives:

    def test_single_value_returns_zeros(self):
        assert _compute_derivatives([10]) == (0.0, 0.0)

    def test_two_values_first_deriv_only(self):
        first, second = _compute_derivatives([5, 15])
        assert first == 10.0
        assert second == 0.0

    def test_three_values_both_derivs(self):
        # counts: 5, 10, 20 → Δ=[5,10] → first=10, second=5
        first, second = _compute_derivatives([5, 10, 20])
        assert first == 10.0
        assert second == 5.0

    def test_falling_rate_negative_deriv(self):
        first, second = _compute_derivatives([100, 50, 10])
        assert first == -40.0
        assert second == 10.0   # deceleration of the fall

    def test_stable_series_zero_derivs(self):
        first, second = _compute_derivatives([10, 10, 10, 10])
        assert first == 0.0
        assert second == 0.0

    def test_empty_list_returns_zeros(self):
        assert _compute_derivatives([]) == (0.0, 0.0)


class TestNormaliseVelocityScore:

    def test_zero_input(self):
        assert _normalise_velocity_score(0, 0.0, 0.0) == 0.0

    def test_high_acceleration_boosts_score(self):
        # high second derivative should push score higher than just count alone
        score_no_accel = _normalise_velocity_score(100, 0.0, 0.0)
        score_with_accel = _normalise_velocity_score(100, 0.0, 50.0)
        assert score_with_accel > score_no_accel

    def test_score_capped_at_100(self):
        # Extreme values should still be capped
        score = _normalise_velocity_score(99999, 99999.0, 99999.0)
        assert score == 100.0

    def test_score_in_valid_range(self):
        for count in [0, 50, 200, 500, 1000]:
            score = _normalise_velocity_score(count, float(count * 0.1), float(count * 0.05))
            assert 0.0 <= score <= 100.0
