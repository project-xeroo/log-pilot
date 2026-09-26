"""Log ingestion models (Phase 1): upload sessions and parsed log records."""
from __future__ import annotations

import enum

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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .base import Base


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


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum *values* (e.g. 'pending'), matching the Postgres enum types."""
    return [m.value for m in enum_cls]


# ---------------------------------------------------------------------------
# log_sessions — one row per uploaded file or streaming session
# ---------------------------------------------------------------------------


class LogSession(Base):
    __tablename__ = "log_sessions"

    # Source metadata
    filename = Column(String(512), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    source_type = Column(String(64), nullable=False, default="upload")  # upload | api | stream
    content_type = Column(String(128), nullable=True)
    storage_key = Column(String(1024), nullable=True)  # object storage path

    # Processing state
    status = Column(
        Enum(IngestionStatus, name="ingestionstatus", values_callable=enum_values),
        nullable=False,
        default=IngestionStatus.PENDING,
    )
    detected_format = Column(
        Enum(LogFormat, name="logformat", values_callable=enum_values), nullable=True
    )
    total_lines = Column(Integer, nullable=True)
    parsed_records = Column(Integer, nullable=True, default=0)
    failed_records = Column(Integer, nullable=True, default=0)
    pii_redacted_count = Column(Integer, nullable=True, default=0)
    error_message = Column(Text, nullable=True)

    # Auth / ownership
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True)

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

    # High-volume table: integer PK and no updated_at (records are immutable)
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    updated_at = None

    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("log_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Parsed fields
    timestamp = Column(DateTime(timezone=True), nullable=True)
    service_name = Column(String(256), nullable=True)
    severity = Column(
        Enum(SeverityLevel, name="severitylevel", values_callable=enum_values),
        nullable=False,
        default=SeverityLevel.UNKNOWN,
    )
    message = Column(Text, nullable=True)
    # message_tsv (generated tsvector) and embedding (pgvector) are managed by
    # migrations only and queried via raw SQL, so they are not mapped here.
    request_id = Column(String(256), nullable=True)
    trace_id = Column(String(256), nullable=True)
    environment = Column(String(128), nullable=True)
    deployment_version = Column(String(128), nullable=True)
    source_ip = Column(String(64), nullable=True)
    http_method = Column(String(16), nullable=True)
    http_path = Column(String(2048), nullable=True)
    http_status = Column(Integer, nullable=True)
    duration_ms = Column(Float, nullable=True)
    log_format = Column(
        Enum(LogFormat, name="logformat", values_callable=enum_values),
        nullable=False,
        default=LogFormat.UNKNOWN,
    )

    # Raw / extras
    raw_line = Column(Text, nullable=True)  # original line pre-redaction kept only if no PII
    extra_fields = Column(JSONB, nullable=True)  # additional parsed k/v pairs

    # PII & malformed flags
    pii_was_redacted = Column(Boolean, nullable=False, default=False)
    is_malformed = Column(Boolean, nullable=False, default=False)

    session = relationship("LogSession", back_populates="records")

    __table_args__ = (
        Index("ix_log_records_timestamp", "timestamp"),
        Index("ix_log_records_session_id", "session_id"),
        Index("ix_log_records_service_name", "service_name"),
        Index("ix_log_records_severity", "severity"),
        Index("ix_log_records_trace_id", "trace_id"),
        Index("ix_log_records_request_id", "request_id"),
        Index("ix_log_records_service_ts", "service_name", "timestamp"),
    )
