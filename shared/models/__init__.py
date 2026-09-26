"""Shared SQLAlchemy ORM models for LogPilot services."""
from __future__ import annotations

from .base import Base
# Phase 1 — Ingestion
from .logs import SeverityLevel, LogFormat, IngestionStatus, LogSession, LogRecord
from .users import Role, Permission, ROLE_PERMISSIONS, has_permission, User
from .audit import AutonomyTier, AgentAction
# Forecasting core
from .service import MonitoredService
from .velocity import ErrorVelocityWindow
from .snapshot import RiskSnapshot
from .alert import PreIncidentAlert
from .premortem import PreMortemReport
from .autonomy import AutonomyPolicy
# Phase 3 — Analysis & Correlation Layer
from .analysis import (
    DeduplicatedError,
    ErrorCluster,
    ServiceHealthState,
    AnomalyEvent,
    DeploymentRegression,
)
# Phase 5 — Reporting & Feedback
from .reports import (
    ReportStatus,
    IncidentReport,
    OutcomeVerdict,
    IncidentOutcome,
    ForecastWeight,
    DeploymentSnapshot,
)

__all__ = [
    "Base",
    # Phase 1
    "SeverityLevel",
    "LogFormat",
    "IngestionStatus",
    "LogSession",
    "LogRecord",
    "Role",
    "Permission",
    "ROLE_PERMISSIONS",
    "has_permission",
    "User",
    "AutonomyTier",
    "AgentAction",
    # Forecasting core
    "MonitoredService",
    "ErrorVelocityWindow",
    "RiskSnapshot",
    "PreIncidentAlert",
    "PreMortemReport",
    "AutonomyPolicy",
    # Phase 3
    "DeduplicatedError",
    "ErrorCluster",
    "ServiceHealthState",
    "AnomalyEvent",
    "DeploymentRegression",
    # Phase 5
    "ReportStatus",
    "IncidentReport",
    "OutcomeVerdict",
    "IncidentOutcome",
    "ForecastWeight",
    "DeploymentSnapshot",
]
