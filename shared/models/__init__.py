<<<<<<< HEAD
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class Role(str, enum.Enum):
    admin = "admin"
    developer = "developer"
    sre = "sre"
    viewer = "viewer"


class Permission(str, enum.Enum):
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


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.admin: set(Permission),          # all permissions
    Role.sre: {
        Permission.report_create,
        Permission.report_read,
        Permission.report_update,
        Permission.report_export,
        Permission.outcome_write,
        Permission.outcome_read,
        Permission.deployment_read,
        Permission.deployment_compare,
        Permission.forecast_read,
        Permission.alert_read,
        Permission.alert_manage,
    },
    Role.developer: {
        Permission.report_read,
        Permission.report_export,
        Permission.outcome_read,
        Permission.deployment_read,
        Permission.deployment_compare,
        Permission.forecast_read,
        Permission.alert_read,
    },
    Role.viewer: {
        Permission.report_read,
        Permission.deployment_read,
        Permission.forecast_read,
        Permission.alert_read,
        Permission.outcome_read,
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    reports: Mapped[list["IncidentReport"]] = relationship(
        back_populates="author", lazy="select"
    )


# ---------------------------------------------------------------------------
# Incident Report
# ---------------------------------------------------------------------------


class ReportStatus(str, enum.Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    exported = "exported"


class IncidentReport(Base):
    __tablename__ = "incident_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus), nullable=False, default=ReportStatus.draft
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Structured sections — stored as text so agents can write free-form prose
    summary: Mapped[str | None] = mapped_column(Text)
    timeline: Mapped[str | None] = mapped_column(Text)          # markdown table or prose
    affected_services: Mapped[list[str] | None] = mapped_column(JSON)
    impact_analysis: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    preventive_actions: Mapped[str | None] = mapped_column(Text)

    # Metadata
    incident_id: Mapped[str | None] = mapped_column(String(255))   # link to alert/anomaly
    severity: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ttd_seconds: Mapped[float | None] = mapped_column(Float)        # time-to-detect
    ttr_seconds: Mapped[float | None] = mapped_column(Float)        # time-to-resolve

    # Agent generation metadata
    generation_model: Mapped[str | None] = mapped_column(String(100))
    generation_prompt_version: Mapped[str | None] = mapped_column(String(50))
    generation_duration_ms: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    author: Mapped["User | None"] = relationship(back_populates="reports")
    outcomes: Mapped[list["IncidentOutcome"]] = relationship(
        back_populates="report", lazy="select"
    )


# ---------------------------------------------------------------------------
# Incident Outcome  (feedback loop)
# ---------------------------------------------------------------------------


class OutcomeVerdict(str, enum.Enum):
    true_positive = "true_positive"     # incident was real; prediction was correct
    false_positive = "false_positive"   # alert fired but no real incident
    true_negative = "true_negative"     # no alert; no incident (informational)
    false_negative = "false_negative"   # incident happened; was NOT predicted


class IncidentOutcome(Base):
    __tablename__ = "incident_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_reports.id"), nullable=True
    )
    incident_id: Mapped[str] = mapped_column(String(255), nullable=False)

    verdict: Mapped[OutcomeVerdict] = mapped_column(
        Enum(OutcomeVerdict), nullable=False
    )
    # Was the agent's root-cause / forecast accurate?
    rca_accurate: Mapped[bool | None] = mapped_column(Boolean)
    forecast_accurate: Mapped[bool | None] = mapped_column(Boolean)

    # Time metrics
    time_to_detect_seconds: Mapped[float | None] = mapped_column(Float)
    time_to_resolve_seconds: Mapped[float | None] = mapped_column(Float)
    action_taken: Mapped[str | None] = mapped_column(Text)    # free-form description

    # Leading-indicator signatures that fired (for weight feedback)
    fired_indicators: Mapped[list[str] | None] = mapped_column(JSON)
    # Forecasting score at time of incident
    forecast_score_at_incident: Mapped[float | None] = mapped_column(Float)

    # Free-form notes from the reviewer
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    report: Mapped["IncidentReport | None"] = relationship(back_populates="outcomes")


# ---------------------------------------------------------------------------
# Forecasting Weight (persisted feedback-loop state)
# ---------------------------------------------------------------------------


class ForecastWeight(Base):
    __tablename__ = "forecast_weights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    indicator_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Running accuracy stats
    true_positive_count: Mapped[int] = mapped_column(default=0)
    false_positive_count: Mapped[int] = mapped_column(default=0)
    false_negative_count: Mapped[int] = mapped_column(default=0)
    total_fired: Mapped[int] = mapped_column(default=0)
    precision: Mapped[float] = mapped_column(Float, default=0.0)  # tp / (tp+fp)
    recall: Mapped[float] = mapped_column(Float, default=0.0)     # tp / (tp+fn)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Deployment snapshot (used by Deployment Comparison screen)
# ---------------------------------------------------------------------------


class DeploymentSnapshot(Base):
    __tablename__ = "deployment_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False, default="production")
    version: Mapped[str] = mapped_column(String(255), nullable=False)
    deployed_by: Mapped[str | None] = mapped_column(String(255))
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(JSON, name="metadata")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
=======
"""Shared SQLAlchemy ORM models for LogPilot services."""
from __future__ import annotations

from .base import Base
from .service import MonitoredService
from .velocity import ErrorVelocityWindow
from .snapshot import RiskSnapshot
from .alert import PreIncidentAlert
from .premortem import PreMortemReport
from .autonomy import AutonomyPolicy
from .audit import AgentAction

__all__ = [
    "Base",
    "MonitoredService",
    "ErrorVelocityWindow",
    "RiskSnapshot",
    "PreIncidentAlert",
    "PreMortemReport",
    "AutonomyPolicy",
    "AgentAction",
]
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
