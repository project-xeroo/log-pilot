"""
Phase 1 initial schema migration.

Creates:
  - users
  - log_sessions
  - log_records  (with indexes for date-partitioning, FTS, regex, service+time, vectors)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_phase1_initial"
down_revision = None
branch_labels = None
depends_on = None


def _create_enum(name: str, *values: str) -> None:
    """CREATE TYPE is not idempotent in Postgres, so guard it explicitly."""
    labels = ", ".join(f"'{v}'" for v in values)
    op.execute(f"""
        DO $$ BEGIN
            CREATE TYPE {name} AS ENUM ({labels});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


SEVERITY = ("TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL", "UNKNOWN")
LOG_FORMAT = ("apache_common", "apache_combined", "nginx", "json", "syslog", "custom", "unknown")
INGESTION_STATUS = ("pending", "processing", "completed", "failed", "partial")
USER_ROLE = ("admin", "sre", "developer", "manager", "junior", "viewer")


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Enums
    _create_enum("severitylevel", *SEVERITY)
    _create_enum("logformat", *LOG_FORMAT)
    _create_enum("ingestionstatus", *INGESTION_STATUS)
    _create_enum("userrole", *USER_ROLE)

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(128), nullable=False),
        sa.Column("full_name", sa.String(256), nullable=True),
        sa.Column("role", postgresql.ENUM(*USER_ROLE, name="userrole", create_type=False), nullable=False, server_default="developer"),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.UniqueConstraint("email", "organization_id", name="uq_users_email_org"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # log_sessions
    op.create_table(
        "log_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="upload"),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("status", postgresql.ENUM(*INGESTION_STATUS, name="ingestionstatus", create_type=False), nullable=False, server_default="pending"),
        sa.Column("detected_format", postgresql.ENUM(*LOG_FORMAT, name="logformat", create_type=False), nullable=True),
        sa.Column("total_lines", sa.Integer, nullable=True),
        sa.Column("parsed_records", sa.Integer, nullable=True, server_default="0"),
        sa.Column("failed_records", sa.Integer, nullable=True, server_default="0"),
        sa.Column("pii_redacted_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_log_sessions_status", "log_sessions", ["status"])
    op.create_index("ix_log_sessions_created_at", "log_sessions", ["created_at"])
    op.create_index("ix_log_sessions_organization_id", "log_sessions", ["organization_id"])

    # log_records
    op.create_table(
        "log_records",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("log_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_name", sa.String(256), nullable=True),
        sa.Column("severity", postgresql.ENUM(*SEVERITY, name="severitylevel", create_type=False), nullable=False, server_default="UNKNOWN"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("request_id", sa.String(256), nullable=True),
        sa.Column("trace_id", sa.String(256), nullable=True),
        sa.Column("environment", sa.String(128), nullable=True),
        sa.Column("deployment_version", sa.String(128), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("http_method", sa.String(16), nullable=True),
        sa.Column("http_path", sa.String(2048), nullable=True),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Float, nullable=True),
        sa.Column("log_format", postgresql.ENUM(*LOG_FORMAT, name="logformat", create_type=False), nullable=False, server_default="unknown"),
        sa.Column("raw_line", sa.Text, nullable=True),
        sa.Column("extra_fields", postgresql.JSONB, nullable=True),
        sa.Column("pii_was_redacted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_malformed", sa.Boolean, nullable=False, server_default="false"),
    )
    # Full-text search column (generated)
    op.execute("""
        ALTER TABLE log_records
        ADD COLUMN IF NOT EXISTS message_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(message, ''))) STORED
    """)
    # Indexes
    op.create_index("ix_log_records_timestamp", "log_records", ["timestamp"])
    op.create_index("ix_log_records_session_id", "log_records", ["session_id"])
    op.create_index("ix_log_records_service_name", "log_records", ["service_name"])
    op.create_index("ix_log_records_severity", "log_records", ["severity"])
    op.create_index("ix_log_records_trace_id", "log_records", ["trace_id"])
    op.create_index("ix_log_records_request_id", "log_records", ["request_id"])
    op.create_index("ix_log_records_service_ts", "log_records", ["service_name", "timestamp"])
    op.execute("CREATE INDEX ix_log_records_message_tsv ON log_records USING gin(message_tsv)")
    # Trigram index so regex (~*) keyword search stays under the 500ms target
    op.execute("CREATE INDEX ix_log_records_message_trgm ON log_records USING gin(message gin_trgm_ops)")

    # Vector column + ANN index for semantic search
    op.execute("ALTER TABLE log_records ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    op.execute("""
        CREATE INDEX ix_log_records_embedding_ivfflat
        ON log_records USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    op.drop_table("log_records")
    op.drop_table("log_sessions")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS severitylevel")
    op.execute("DROP TYPE IF EXISTS logformat")
    op.execute("DROP TYPE IF EXISTS ingestionstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
