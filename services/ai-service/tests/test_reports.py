"""Incident report drafting falls back to a structured stub without an API key."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_generate_incident_report_stub(monkeypatch):
    from app.config import settings
    from app.reports import generate_incident_report

    monkeypatch.setattr(settings, "openai_api_key", "")

    report = await generate_incident_report(
        incident_id="INC-1",
        title="Checkout outage",
        severity="high",
        started_at=None,
        resolved_at=None,
        affected_services=["checkout"],
        context_logs=None,
    )

    for section in ("summary", "timeline", "impact_analysis", "root_cause", "resolution", "preventive_actions"):
        assert report[section]
    assert report["affected_services"] == ["checkout"]
    assert report["model"] == "stub"
