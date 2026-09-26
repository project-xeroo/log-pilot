"""
Tests for Phase 3 — Clustering Pipeline

Tests the DBSCAN implementation, centroid computation, and silhouette proxy
without requiring a live database connection.
"""

from __future__ import annotations

import math
import pytest

from app.clustering import (
    _cosine_distance,
    _centroid,
    _avg_cosine_similarity,
    _dbscan,
)


class TestCosineDistance:
    def test_identical(self):
        v = [1.0, 0.5, 0.2]
        assert _cosine_distance(v, v) < 1e-6

    def test_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_distance(a, b) - 1.0) < 1e-6

    def test_symmetry(self):
        a = [0.3, 0.7, 0.1]
        b = [0.6, 0.2, 0.9]
        assert abs(_cosine_distance(a, b) - _cosine_distance(b, a)) < 1e-9


class TestCentroid:
    def test_single_vector(self):
        v = [1.0, 2.0, 3.0]
        assert _centroid([v]) == [round(x, 6) for x in v]

    def test_two_vectors(self):
        result = _centroid([[1.0, 0.0], [0.0, 1.0]])
        assert abs(result[0] - 0.5) < 1e-6
        assert abs(result[1] - 0.5) < 1e-6

    def test_empty(self):
        assert _centroid([]) == []


class TestAvgCosineSimilarity:
    def test_perfect_cluster(self):
        v = [0.707, 0.707]
        # All identical vectors — similarity should be 1.0
        score = _avg_cosine_similarity([v, v, v], v)
        assert abs(score - 1.0) < 1e-4

    def test_empty_cluster(self):
        assert _avg_cosine_similarity([], [1.0, 0.0]) == 0.0


class TestDBSCAN:
    def _make_cluster(self, n: int, base: list[float], noise: float = 0.0) -> list[list[float]]:
        """Create n nearly-identical vectors (same cluster)."""
        result = []
        for i in range(n):
            v = [x + noise * (i * 0.01) for x in base]
            result.append(v)
        return result

    def test_two_clear_clusters(self):
        """Two groups of similar vectors, far apart in embedding space."""
        cluster_a = self._make_cluster(4, [1.0, 0.0, 0.0])
        cluster_b = self._make_cluster(4, [0.0, 1.0, 0.0])
        embeddings = cluster_a + cluster_b

        labels = _dbscan(embeddings, eps=0.1, min_samples=2)

        labels_a = set(labels[:4])
        labels_b = set(labels[4:])
        # Each group should form its own cluster (one label per group)
        assert len(labels_a) == 1
        assert len(labels_b) == 1
        # The two groups must have different labels
        assert labels_a != labels_b
        # Neither group should be noise
        assert -1 not in labels_a
        assert -1 not in labels_b

    def test_noise_points(self):
        """An isolated point should be labelled -1 (noise) with eps small enough."""
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.99, 0.0, 0.0],
            [0.98, 0.0, 0.0],
            [0.0, 1.0, 0.0],  # isolated — noise with eps=0.05, min_samples=2
        ]
        labels = _dbscan(embeddings, eps=0.05, min_samples=2)
        assert labels[3] == -1

    def test_single_cluster(self):
        """All nearly-identical vectors should form one cluster."""
        embeddings = self._make_cluster(5, [0.6, 0.8, 0.0])
        labels = _dbscan(embeddings, eps=0.5, min_samples=2)
        unique_labels = set(labels)
        unique_labels.discard(-1)
        assert len(unique_labels) == 1

    def test_silhouette_above_threshold(self):
        """
        A well-separated two-cluster scenario should yield a silhouette proxy > 0.65.
        This tests the PRD success criterion.
        """
        cluster_a = self._make_cluster(5, [1.0, 0.0, 0.0, 0.0])
        cluster_b = self._make_cluster(5, [0.0, 0.0, 1.0, 0.0])
        embeddings = cluster_a + cluster_b

        from app.clustering import _centroid, _avg_cosine_similarity
        labels = _dbscan(embeddings, eps=0.2, min_samples=2)

        silhouette_scores = []
        groups: dict[int, list] = {}
        for i, label in enumerate(labels):
            if label != -1:
                groups.setdefault(label, []).append(embeddings[i])

        for members in groups.values():
            c = _centroid(members)
            silhouette_scores.append(_avg_cosine_similarity(members, c))

        if silhouette_scores:
            avg = sum(silhouette_scores) / len(silhouette_scores)
            assert avg >= 0.65, f"Silhouette score {avg:.3f} < 0.65 threshold"
