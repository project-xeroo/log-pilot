"""Users and RBAC (PRD §10): roles, permissions, and the users table."""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Column, Enum, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base
from .logs import enum_values


class Role(str, enum.Enum):
    admin = "admin"
    sre = "sre"
    developer = "developer"
    manager = "manager"   # Engineering Manager persona: reviews and exports reports
    junior = "junior"     # Junior Engineer / Trainee: guided mode, no approvals
    viewer = "viewer"


class Permission(str, enum.Enum):
    # Logs, search, chat, feed (Phase 1–2)
    logs_upload = "logs:upload"
    search_read = "search:read"
    chat_use = "chat:use"
    feed_read = "feed:read"
    # Reports
    report_create = "report:create"
    report_read = "report:read"
    report_update = "report:update"
    report_export = "report:export"
    report_delete = "report:delete"
    # Outcomes
    outcome_write = "outcome:write"
    outcome_read = "outcome:read"
    # Deployments
    deployment_read = "deployment:read"
    deployment_compare = "deployment:compare"
    # Users / admin
    user_manage = "user:manage"
    # Forecasting
    forecast_read = "forecast:read"
    # Alerts
    alert_read = "alert:read"
    alert_manage = "alert:manage"


_VIEWER: set[Permission] = {
    Permission.search_read,
    Permission.feed_read,
    Permission.report_read,
    Permission.deployment_read,
    Permission.forecast_read,
    Permission.alert_read,
    Permission.outcome_read,
}

_DEVELOPER: set[Permission] = _VIEWER | {
    Permission.logs_upload,
    Permission.chat_use,
    Permission.report_export,
    Permission.deployment_compare,
}

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.admin: set(Permission),
    Role.sre: _DEVELOPER | {
        Permission.report_create,
        Permission.report_update,
        Permission.outcome_write,
        Permission.alert_manage,
    },
    Role.developer: _DEVELOPER,
    # Same access as Developer; approvals are withheld until promoted (PRD §9.3)
    Role.junior: _DEVELOPER,
    Role.manager: _VIEWER | {Permission.chat_use, Permission.report_export},
    Role.viewer: _VIEWER,
}


def has_permission(role: Role | str, permission: Permission) -> bool:
    try:
        role = Role(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(role, set())


class User(Base):
    __tablename__ = "users"

    email = Column(String(320), nullable=False)
    hashed_password = Column(String(128), nullable=False)
    full_name = Column(String(256), nullable=True)
    role = Column(
        Enum(Role, name="userrole", values_callable=enum_values),
        nullable=False,
        default=Role.developer,
    )
    organization_id = Column(UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    reports = relationship("IncidentReport", back_populates="author", lazy="select")

    __table_args__ = (
        UniqueConstraint("email", "organization_id", name="uq_users_email_org"),
        Index("ix_users_email", "email"),
    )
