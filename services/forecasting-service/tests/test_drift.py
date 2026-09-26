"""
Unit tests for cosine similarity calculation in the drift detector.
Tests the pure _cosine_similarity helper — no DB required.
"""

import math
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.drift.detector import _cosine_similarity


class TestCosineSimilarity:

    def test_identical_vectors_returns_1(self):
        v = [1.0, 0.5, 0.3]
        assert math.isclose(_cosine_similarity(v, v), 1.0, rel_tol=1e-6)

    def test_orthogonal_vectors_returns_0(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert math.isclose(_cosine_similarity(a, b), 0.0, abs_tol=1e-9)

    def test_opposite_vectors_returns_minus_1(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert math.isclose(_cosine_similarity(a, b), -1.0, rel_tol=1e-6)

    def test_zero_vector_returns_1(self):
        # Defined to return 1 (no drift) when a vector is all zeros
        z = [0.0, 0.0, 0.0]
        assert _cosine_similarity(z, z) == 1.0

    def test_symmetry(self):
        a = [0.3, 0.7, 0.1]
        b = [0.9, 0.2, 0.5]
        assert math.isclose(_cosine_similarity(a, b), _cosine_similarity(b, a), rel_tol=1e-9)

    def test_scaled_vector_same_similarity(self):
        a = [1.0, 2.0, 3.0]
        b = [2.0, 4.0, 6.0]   # same direction, doubled magnitude
        assert math.isclose(_cosine_similarity(a, b), 1.0, rel_tol=1e-6)

    def test_high_dimensional_vector(self):
        dims = 1536
        a = [math.sin(i) for i in range(dims)]
        b = [math.sin(i) for i in range(dims)]
        assert math.isclose(_cosine_similarity(a, b), 1.0, rel_tol=1e-6)
