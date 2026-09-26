"""
Tests for Phase 3 — Deduplication Pipeline

Tests the fingerprint normalisation, cosine similarity, and centroid update logic
without requiring a live database connection.
"""

from __future__ import annotations

import math
import pytest

from app.deduplication import (
    _normalise_message,
    _fingerprint,
    _cosine_similarity,
    _update_centroid,
)


class TestNormaliseMessage:
    def test_strips_uuid(self):
        msg = "Error processing request 550e8400-e29b-41d4-a716-446655440000 failed"
        normalised = _normalise_message(msg)
        assert "<uuid>" in normalised
        assert "550e8400" not in normalised

    def test_strips_long_hex(self):
        msg = "Token abc123def456789012 is invalid"
        normalised = _normalise_message(msg)
        assert "<hex>" in normalised

    def test_strips_ip(self):
        msg = "Connection refused from 192.168.1.100"
        normalised = _normalise_message(msg)
        assert "<ip>" in normalised
        assert "192.168.1.100" not in normalised

    def test_strips_large_numbers(self):
        msg = "Record ID 12345678 not found"
        normalised = _normalise_message(msg)
        assert "<num>" in normalised

    def test_preserves_error_text(self):
        msg = "NullPointerException in checkout.service"
        normalised = _normalise_message(msg)
        assert "nullpointerexception" in normalised

    def test_lowercases(self):
        msg = "ERROR: Database connection failed"
        assert _normalise_message(msg) == _normalise_message(msg.lower())


class TestFingerprint:
    def test_deterministic(self):
        msg = "Database connection timeout after 30 seconds"
        assert _fingerprint(msg) == _fingerprint(msg)

    def test_different_ids_same_fingerprint(self):
        msg1 = "Connection to db-12345678 failed"
        msg2 = "Connection to db-87654321 failed"
        # After stripping numbers, these should produce the same fingerprint
        assert _fingerprint(msg1) == _fingerprint(msg2)

    def test_different_errors_different_fingerprint(self):
        msg1 = "NullPointerException in service"
        msg2 = "DatabaseException in service"
        assert _fingerprint(msg1) != _fingerprint(msg2)

    def test_fingerprint_length(self):
        fp = _fingerprint("any message")
        assert len(fp) == 64


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0, 1.0]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_similar_vectors(self):
        a = [1.0, 0.9, 0.1]
        b = [0.9, 1.0, 0.0]
        score = _cosine_similarity(a, b)
        assert 0.9 < score < 1.0


class TestUpdateCentroid:
    def test_moves_toward_new_vector(self):
        current = [1.0, 0.0]
        new_vec = [0.0, 1.0]
        updated = _update_centroid(current, new_vec, count=2, alpha=0.5)
        assert updated[0] < 1.0
        assert updated[1] > 0.0

    def test_stays_same_with_identical(self):
        current = [0.5, 0.5]
        updated = _update_centroid(current, current, count=10, alpha=0.1)
        assert abs(updated[0] - 0.5) < 1e-5
        assert abs(updated[1] - 0.5) < 1e-5
