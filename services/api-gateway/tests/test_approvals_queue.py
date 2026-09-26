"""
Integration-style tests for the approvals queue endpoints.
Uses FastAPI TestClient with an in-memory SQLite DB (no real Postgres needed).

Tests cover:
- GET  /forecasting/alerts           — list open alerts
- POST /forecasting/alerts/{id}/approve
- POST /forecasting/alerts/{id}/edit
- POST /forecasting/alerts/{id}/dismiss
- Role enforcement: viewer cannot approve
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from shared.models import Base, PreIncidentAlert, MonitoredService
from shared.config import get_db
from app.auth.jwt_auth import create_access_token

# Use in-memory SQLite for tests
_TEST_DB_URL = "sqlite://"
_engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})

# SQLite doesn't support UUID natively — patch models for test
from sqlalchemy.pool import StaticPool
_test_engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def _get_test_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    # Create tables
    Base.metadata.create_all(bind=_test_engine)

    # Import app after patching
    from services.api_gateway.app.main import app
    app.dependency_overrides[get_db] = _get_test_db

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=_test_engine)


def _sre_token():
    return create_access_token("test-sre", "sre")


def _viewer_token():
    return create_access_token("test-viewer", "viewer")


def _seed_alert(service_name="test-svc") -> str:
    """Insert a test service + open alert; return alert ID."""
    db = TestingSession()
    try:
        svc_id = uuid.uuid4()
        svc = MonitoredService(id=svc_id, name=service_name, environment="test")
        db.add(svc)
        db.flush()

        alert_id = uuid.uuid4()
        alert = PreIncidentAlert(
            id=alert_id,
            service_id=svc_id,
            risk_score=75.0,
            risk_tier="warning",
            explanation="Test alert from seeder",
            status="open",
            alerted_at=datetime.now(timezone.utc),
            recommended_actions=[{"priority": 1, "action": "Investigate logs"}],
        )
        db.add(alert)
        db.commit()
        return str(alert_id)
    finally:
        db.close()


class TestAlertsQueue:

    def test_list_open_alerts_requires_auth(self, client):
        resp = client.get("/forecasting/alerts")
        assert resp.status_code == 403  # no token

    def test_list_open_alerts_authenticated(self, client):
        headers = {"Authorization": f"Bearer {_viewer_token()}"}
        resp = client.get("/forecasting/alerts", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_approve_alert_as_sre(self, client):
        alert_id = _seed_alert("svc-approve")
        headers = {"Authorization": f"Bearer {_sre_token()}"}
        resp = client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user", "notes": "Looks right"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["handled_by"] == "sre-user"

    def test_approve_alert_as_viewer_forbidden(self, client):
        alert_id = _seed_alert("svc-viewer-block")
        headers = {"Authorization": f"Bearer {_viewer_token()}"}
        resp = client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "viewer-user"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_edit_then_approve(self, client):
        alert_id = _seed_alert("svc-edit")
        sre_headers = {"Authorization": f"Bearer {_sre_token()}"}

        # Edit the action first
        edit_resp = client.post(
            f"/forecasting/alerts/{alert_id}/edit",
            json={"edited_action": "Custom remediation step", "edited_by": "sre-user"},
            headers=sre_headers,
        )
        assert edit_resp.status_code == 200
        assert edit_resp.json()["edited_action"] == "Custom remediation step"

        # Then approve
        approve_resp = client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user"},
            headers=sre_headers,
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

    def test_dismiss_alert_as_sre(self, client):
        alert_id = _seed_alert("svc-dismiss")
        headers = {"Authorization": f"Bearer {_sre_token()}"}
        resp = client.post(
            f"/forecasting/alerts/{alert_id}/dismiss",
            json={"dismissed_by": "sre-user", "reason": "False positive"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_double_approve_returns_409(self, client):
        alert_id = _seed_alert("svc-double")
        headers = {"Authorization": f"Bearer {_sre_token()}"}
        client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user"},
            headers=headers,
        )
        # Second approve should 409
        resp = client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user"},
            headers=headers,
        )
        assert resp.status_code == 409

    def test_alert_not_found_returns_404(self, client):
        headers = {"Authorization": f"Bearer {_sre_token()}"}
        fake_id = uuid.uuid4()
        resp = client.post(
            f"/forecasting/alerts/{fake_id}/approve",
            json={"approved_by": "sre-user"},
            headers=headers,
        )
        assert resp.status_code == 404
