"""
Integration-style tests for the approvals queue endpoints.
Uses an in-memory async SQLite DB (no real Postgres or Redis needed).

Tests cover:
- GET  /forecasting/alerts           — list open alerts
- POST /forecasting/alerts/{id}/approve
- POST /forecasting/alerts/{id}/edit
- POST /forecasting/alerts/{id}/dismiss
- Role enforcement: viewer cannot approve
"""

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from shared.models import Base, AgentAction, MonitoredService, PreIncidentAlert, RiskSnapshot
from shared.config import get_db
from app.auth import create_access_token

# Only the tables these endpoints touch (others use Postgres-only types)
_TABLES = [t.__table__ for t in (MonitoredService, RiskSnapshot, PreIncidentAlert, AgentAction)]


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(session_factory):
    from app.main import app

    async def _get_test_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = _get_test_db
    # ASGITransport skips the lifespan, so the Redis event relay is not started
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _auth(role: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uuid.uuid4(), role)}"}


async def _seed_alert(session_factory, service_name="test-svc") -> str:
    """Insert a test service + open alert; return alert ID."""
    async with session_factory() as db:
        svc_id = uuid.uuid4()
        db.add(MonitoredService(id=svc_id, name=service_name, environment="test"))
        await db.flush()

        alert_id = uuid.uuid4()
        db.add(PreIncidentAlert(
            id=alert_id,
            service_id=svc_id,
            risk_score=75.0,
            risk_tier="warning",
            explanation="Test alert from seeder",
            status="open",
            alerted_at=datetime.now(timezone.utc),
            recommended_actions=[{"priority": 1, "action": "Investigate logs"}],
        ))
        await db.commit()
        return str(alert_id)


class TestAlertsQueue:

    async def test_list_open_alerts_requires_auth(self, client):
        resp = await client.get("/forecasting/alerts")
        assert resp.status_code in (401, 403)  # no token

    async def test_list_open_alerts_authenticated(self, client, session_factory):
        await _seed_alert(session_factory, "svc-list")
        resp = await client.get("/forecasting/alerts", headers=_auth("viewer"))
        assert resp.status_code == 200
        assert [a["status"] for a in resp.json()] == ["open"]

    async def test_approve_alert_as_sre(self, client, session_factory):
        alert_id = await _seed_alert(session_factory, "svc-approve")
        resp = await client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user", "notes": "Looks right"},
            headers=_auth("sre"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["handled_by"] == "sre-user"

    @pytest.mark.parametrize("role", ["viewer", "junior", "developer", "manager"])
    async def test_approve_alert_forbidden_without_sre_role(self, client, session_factory, role):
        alert_id = await _seed_alert(session_factory, f"svc-block-{role}")
        resp = await client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": f"{role}-user"},
            headers=_auth(role),
        )
        assert resp.status_code == 403

    async def test_edit_then_approve(self, client, session_factory):
        alert_id = await _seed_alert(session_factory, "svc-edit")
        sre_headers = _auth("sre")

        # Edit the action first
        edit_resp = await client.post(
            f"/forecasting/alerts/{alert_id}/edit",
            json={"edited_action": "Custom remediation step", "edited_by": "sre-user"},
            headers=sre_headers,
        )
        assert edit_resp.status_code == 200
        assert edit_resp.json()["edited_action"] == "Custom remediation step"

        # Then approve
        approve_resp = await client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user"},
            headers=sre_headers,
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

    async def test_dismiss_alert_as_sre(self, client, session_factory):
        alert_id = await _seed_alert(session_factory, "svc-dismiss")
        resp = await client.post(
            f"/forecasting/alerts/{alert_id}/dismiss",
            json={"dismissed_by": "sre-user", "reason": "False positive"},
            headers=_auth("sre"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    async def test_double_approve_returns_409(self, client, session_factory):
        alert_id = await _seed_alert(session_factory, "svc-double")
        headers = _auth("sre")
        await client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user"},
            headers=headers,
        )
        # Second approve should 409
        resp = await client.post(
            f"/forecasting/alerts/{alert_id}/approve",
            json={"approved_by": "sre-user"},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_alert_not_found_returns_404(self, client):
        resp = await client.post(
            f"/forecasting/alerts/{uuid.uuid4()}/approve",
            json={"approved_by": "sre-user"},
            headers=_auth("sre"),
        )
        assert resp.status_code == 404
