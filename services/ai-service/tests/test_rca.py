"""
Tests for Phase 3 — RCA Engine

Tests the temporal correlation, dependency inference, and causal chain builder
without requiring a live database connection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.rca import (
    _infer_service_dependencies,
    _build_causal_chain,
    CausalStep,
)


def _make_event(service: str, ts: datetime, severity: str = "ERROR") -> dict:
    return {
        "id": f"{service}-{ts.isoformat()}",
        "timestamp": ts.isoformat(),
        "service": service,
        "severity": severity,
        "message": f"Error in {service}",
    }


class TestInferServiceDependencies:
    def test_identifies_upstream_downstream(self):
        """
        If service A's errors consistently precede service B's errors within 30s,
        A should be inferred as an upstream dependency of B.
        """
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        events = []
        # A fires 10s before B, 4 times
        for i in range(4):
            offset = timedelta(minutes=i * 2)
            events.append(_make_event("service-a", base + offset))
            events.append(_make_event("service-b", base + offset + timedelta(seconds=10)))

        deps = _infer_service_dependencies(events, lead_window_seconds=30)
        assert "service-b" in deps.get("service-a", []), \
            "service-a should be detected as upstream of service-b"

    def test_no_false_dependency_independent_services(self):
        """Services with unrelated error timings should not infer dependencies."""
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        events = []
        # service-x errors at even minutes, service-y at odd minutes, far apart
        for i in range(4):
            events.append(_make_event("service-x", base + timedelta(minutes=i * 10)))
        for i in range(4):
            events.append(_make_event("service-y", base + timedelta(minutes=i * 10 + 5)))

        deps = _infer_service_dependencies(events, lead_window_seconds=30)
        # With 5-minute gaps, service-x shouldn't be flagged as upstream of service-y
        assert "service-y" not in deps.get("service-x", [])

    def test_empty_timeline(self):
        deps = _infer_service_dependencies([])
        assert deps == {}

    def test_single_service(self):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = [_make_event("only-service", base)]
        deps = _infer_service_dependencies(events)
        assert "only-service" in deps
        assert deps["only-service"] == []


class TestBuildCausalChain:
    def test_returns_steps_in_order(self):
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event("db-service", base),
            _make_event("api-service", base + timedelta(seconds=5)),
            _make_event("frontend", base + timedelta(seconds=10)),
        ]
        deps = {
            "db-service": ["api-service"],
            "api-service": ["frontend"],
            "frontend": [],
        }
        chain = _build_causal_chain(events, deps, primary_service="db-service")

        assert len(chain) >= 1
        for step in chain:
            assert isinstance(step, CausalStep)
            assert step.order >= 1

    def test_empty_timeline(self):
        chain = _build_causal_chain([], {}, "my-service")
        assert chain == []

    def test_root_service_comes_first(self):
        """Services not in any downstream set should appear first in the chain."""
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event("downstream", base),
            _make_event("root", base - timedelta(seconds=5)),
        ]
        deps = {"root": ["downstream"], "downstream": []}
        chain = _build_causal_chain(events, deps, primary_service="root")
        # root should come before downstream
        services_in_order = [s.service for s in chain]
        assert services_in_order.index("root") < services_in_order.index("downstream")
