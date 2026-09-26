"""Shared SQLAlchemy ORM models for LogPilot services."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SeverityLevel(str, enum.Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"
    UNKNOWN = "UNKNOWN"


class LogFormat(str, enum.Enum):
    APACHE_COMMON = "apache_common"
    APACHE_COMBINED = "apache_combined"
    NGINX = "nginx"
    JSON = "json"
    SYSLOG = "syslog"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AutonomyTier(str, enum.Enum):
    READ_ONLY = "read_only"
    PROPOSE_ONLY = "propose_only"
    AUTONOMOUS = "autonomous"


# ---------------------------------------------------------------------------
# log_sessions — one row per uploaded file or streaming session
# ---------------------------------------------------------------------------


class LogSession(Base):
    __tablename__ = "log_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Source metadata
    filename = Column(String(512), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    source_type = Column(String(64), nullable=False, default="upload")  # upload | api | stream
    content_type = Column(String(128), nullable=True)
    storage_key = Column(String(1024), nullable=True)  # object storage path

    # Processing state
    status = Column(Enum(IngestionStatus), nullable=False, default=IngestionStatus.PENDING)
    detected_format = Column(Enum(LogFormat), nullable=True)
    total_lines = Column(Integer, nullable=True)
    parsed_records = Column(Integer, nullable=True, default=0)
    failed_records = Column(Integer, nullable=True, default=0)
    pii_redacted_count = Column(Integer, nullable=True, default=0)
    error_message = Column(Text, nullable=True)

    # Auth / ownership
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    records = relationship("LogRecord", back_populates="session", passive_deletes=True)

    __table_args__ = (
        Index("ix_log_sessions_status", "status"),
        Index("ix_log_sessions_created_at", "created_at"),
        Index("ix_log_sessions_organization_id", "organization_id"),
    )


# ---------------------------------------------------------------------------
# log_records — one row per parsed log line
# ---------------------------------------------------------------------------


class LogRecord(Base):
    __tablename__ = "log_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("log_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Parsed fields
    timestamp = Column(DateTime(timezone=True), nullable=True)
    service_name = Column(String(256), nullable=True)
    severity = Column(Enum(SeverityLevel), nullable=False, default=SeverityLevel.UNKNOWN)
    message = Column(Text, nullable=True)
    message_tsv = Column(Text, nullable=True)  # tsvector column managed via trigger/index
    request_id = Column(String(256), nullable=True)
    trace_id = Column(String(256), nullable=True)
    environment = Column(String(128), nullable=True)
    deployment_version = Column(String(128), nullable=True)
    source_ip = Column(String(64), nullable=True)
    http_method = Column(String(16), nullable=True)
    http_path = Column(String(2048), nullable=True)
    http_status = Column(Integer, nullable=True)
    duration_ms = Column(Float, nullable=True)
    log_format = Column(Enum(LogFormat), nullable=False, default=LogFormat.UNKNOWN)

    # Raw / extras
    raw_line = Column(Text, nullable=True)  # original line pre-redaction kept only if no PII
    extra_fields = Column(JSONB, nullable=True)  # additional parsed k/v pairs

    # PII & malformed flags
    pii_was_redacted = Column(Boolean, nullable=False, default=False)
    is_malformed = Column(Boolean, nullable=False, default=False)

    # Relationships
    session = relationship("LogSession", back_populates="records")

    __table_args__ = (
        # Date-partitioning friendly index — most queries filter by time range
        Index("ix_log_records_timestamp", "timestamp"),
        Index("ix_log_records_session_id", "session_id"),
        Index("ix_log_records_service_name", "service_name"),
        Index("ix_log_records_severity", "severity"),
        Index("ix_log_records_trace_id", "trace_id"),
        Index("ix_log_records_request_id", "request_id"),
        # Composite for common dashboard query: service + time range
        Index("ix_log_records_service_ts", "service_name", "timestamp"),
    )


# ---------------------------------------------------------------------------
# users — minimal user table for JWT/RBAC (scaffolded for Phase 1)
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SRE = "sre"
    DEVELOPER = "developer"
    MANAGER = "manager"
    JUNIOR = "junior"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    email = Column(String(320), nullable=False)
    hashed_password = Column(String(128), nullable=False)
    full_name = Column(String(256), nullable=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.DEVELOPER)
    organization_id = Column(UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("email", "organization_id", name="uq_users_email_org"),
        Index("ix_users_email", "email"),
    )


# ---------------------------------------------------------------------------
# agent_actions — audit log for every agent action (Phase 1 foundation)
# ---------------------------------------------------------------------------


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tool_name = Column(String(128), nullable=False)          # e.g. "log_ingestion", "pii_redaction"
    trigger = Column(String(64), nullable=False)             # "upload" | "api" | "scheduled" | "user"
    autonomy_tier = Column(Enum(AutonomyTier), nullable=False, default=AutonomyTier.AUTONOMOUS)
    actor_user_id = Column(UUID(as_uuid=True), nullable=True)  # null = autonomous agent
    session_id = Column(UUID(as_uuid=True), nullable=True)
    confidence = Column(Float, nullable=True)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="completed")  # completed | failed | proposed
    error = Column(Text, nullable=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_agent_actions_created_at", "created_at"),
        Index("ix_agent_actions_tool_name", "tool_name"),
        Index("ix_agent_actions_session_id", "session_id"),
        Index("ix_agent_actions_organization_id", "organization_id"),
    )
