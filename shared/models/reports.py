"""Reporting & feedback models (Phase 5): incident reports, outcomes,
forecast weights, and deployment snapshots."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .logs import enum_values


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

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="reportstatus", values_callable=enum_values),
        nullable=False,
        default=ReportStatus.draft,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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

    author = relationship("User", back_populates="reports")
    outcomes = relationship("IncidentOutcome", back_populates="report", lazy="select")


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

    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_reports.id", ondelete="SET NULL"), nullable=True
    )
    # Pre-incident alert this outcome labels (PRD §7.3 incident_outcomes.alert_id)
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pre_incident_alerts.id", ondelete="SET NULL"), nullable=True
    )
    incident_id: Mapped[str] = mapped_column(String(255), nullable=False)

    verdict: Mapped[OutcomeVerdict] = mapped_column(
        Enum(OutcomeVerdict, name="outcomeverdict", values_callable=enum_values),
        nullable=False,
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
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    report = relationship("IncidentReport", back_populates="outcomes")


# ---------------------------------------------------------------------------
# Forecasting Weight (persisted feedback-loop state)
# ---------------------------------------------------------------------------


class ForecastWeight(Base):
    __tablename__ = "forecast_weights"

    indicator_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Running accuracy stats
    true_positive_count: Mapped[int] = mapped_column(default=0)
    false_positive_count: Mapped[int] = mapped_column(default=0)
    false_negative_count: Mapped[int] = mapped_column(default=0)
    total_fired: Mapped[int] = mapped_column(default=0)
    precision: Mapped[float] = mapped_column(Float, default=0.0)  # tp / (tp+fp)
    recall: Mapped[float] = mapped_column(Float, default=0.0)     # tp / (tp+fn)


# ---------------------------------------------------------------------------
# Deployment snapshot (used by Deployment Comparison screen)
# ---------------------------------------------------------------------------


class DeploymentSnapshot(Base):
    __tablename__ = "deployment_snapshots"

    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False, default="production")
    version: Mapped[str] = mapped_column(String(255), nullable=False)
    deployed_by: Mapped[str | None] = mapped_column(String(255))
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
