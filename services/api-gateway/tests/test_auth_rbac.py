"""Tests for JWT handling, the role → permission matrix, and WebSocket fan-out."""

import uuid

import pytest
from fastapi import HTTPException

from shared.models import Permission, Role, has_permission
from app.auth import create_access_token, decode_access_token, permission_checker
from app.websocket import ConnectionManager


def test_token_round_trip():
    user_id = uuid.uuid4()
    payload = decode_access_token(create_access_token(user_id, Role.sre))
    assert payload.id == user_id
    assert payload.role == "sre"


def test_invalid_token_rejected():
    with pytest.raises(HTTPException) as exc:
        decode_access_token("not-a-jwt")
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "role, permission, allowed",
    [
        # Phase 2: every role can search and read the feed; viewers cannot chat
        (Role.viewer, Permission.search_read, True),
        (Role.viewer, Permission.feed_read, True),
        (Role.viewer, Permission.chat_use, False),
        (Role.developer, Permission.chat_use, True),
        (Role.developer, Permission.logs_upload, True),
        # Junior engineers have Developer access but cannot manage alerts (PRD §9.3)
        (Role.junior, Permission.chat_use, True),
        (Role.junior, Permission.alert_manage, False),
        # Engineering managers review and export reports, but do not draft them
        (Role.manager, Permission.report_export, True),
        (Role.manager, Permission.report_create, False),
        (Role.manager, Permission.logs_upload, False),
        (Role.sre, Permission.alert_manage, True),
        (Role.sre, Permission.user_manage, False),
        (Role.admin, Permission.user_manage, True),
    ],
)
def test_role_permissions(role, permission, allowed):
    assert has_permission(role, permission) is allowed


def test_unknown_role_has_no_permissions():
    assert has_permission("devops", Permission.search_read) is False


async def test_permission_checker_blocks_missing_permission():
    token = decode_access_token(create_access_token(uuid.uuid4(), Role.viewer))
    with pytest.raises(HTTPException) as exc:
        await permission_checker(Permission.chat_use)(token)
    assert exc.value.status_code == 403
    assert await permission_checker(Permission.search_read)(token) is token


class _FakeSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def accept(self):
        pass

    async def send_json(self, message):
        self.sent.append(message)


async def test_broadcast_respects_permissions():
    manager = ConnectionManager()
    viewer_ws, sre_ws = _FakeSocket(), _FakeSocket()
    await manager.connect(viewer_ws, "viewer-1", "viewer")
    await manager.connect(sre_ws, "sre-1", "sre")

    await manager.broadcast({"type": "feed_event"}, Permission.feed_read)
    await manager.broadcast({"type": "user_admin_event"}, Permission.user_manage)

    assert [m["type"] for m in viewer_ws.sent] == ["feed_event"]
    assert [m["type"] for m in sre_ws.sent] == ["feed_event"]

    manager.disconnect(viewer_ws, "viewer-1")
    await manager.broadcast({"type": "feed_event"}, Permission.feed_read)
    assert len(viewer_ws.sent) == 1


def test_password_hash_round_trip():
    from app.auth import hash_password, verify_password

    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$2b$")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("anything", "not-a-bcrypt-hash")
