"""
Phase 1 initial schema migration.

Creates:
  - users
  - log_sessions
  - log_records  (with indexes for date-partitioning, FTS, service+time)
  - agent_actions
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_phase1_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")

    # Enums
    op.execute("""
        CREATE TYPE IF NOT EXISTS severitylevel AS ENUM (
            'TRACE','DEBUG','INFO','WARN','WARNING','ERROR','CRITICAL','FATAL','UNKNOWN'
        )
    """)
    op.execute("""
        CREATE TYPE IF NOT EXISTS logformat AS ENUM (
            'apache_common','apache_combined','nginx','json','syslog','custom','unknown'
        )
    """)
    op.execute("""
        CREATE TYPE IF NOT EXISTS ingestionstatus AS ENUM (
            'pending','processing','completed','failed','partial'
        )
    """)
    op.execute("""
        CREATE TYPE IF NOT EXISTS autonomytier AS ENUM (
            'read_only','propose_only','autonomous'
        )
    """)
    op.execute("""
        CREATE TYPE IF NOT EXISTS userrole AS ENUM (
            'admin','sre','developer','manager','junior','viewer'
        )
    """)

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(128), nullable=False),
        sa.Column("full_name", sa.String(256), nullable=True),
        sa.Column("role", sa.Enum("admin", "sre", "developer", "manager", "junior", "viewer", name="userrole"), nullable=False, server_default="developer"),
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
        sa.Column("status", sa.Enum("pending", "processing", "completed", "failed", "partial", name="ingestionstatus"), nullable=False, server_default="pending"),
        sa.Column("detected_format", sa.Enum("apache_common", "apache_combined", "nginx", "json", "syslog", "custom", "unknown", name="logformat"), nullable=True),
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
        sa.Column("severity", sa.Enum("TRACE","DEBUG","INFO","WARN","WARNING","ERROR","CRITICAL","FATAL","UNKNOWN", name="severitylevel"), nullable=False, server_default="UNKNOWN"),
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
        sa.Column("log_format", sa.Enum("apache_common","apache_combined","nginx","json","syslog","custom","unknown", name="logformat"), nullable=False, server_default="unknown"),
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

    # Vector index scaffolding (pgvector — activate when embeddings are generated)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE log_records ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    op.execute("""
        CREATE INDEX ix_log_records_embedding_ivfflat
        ON log_records USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # agent_actions
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=False),
        sa.Column("autonomy_tier", sa.Enum("read_only","propose_only","autonomous", name="autonomytier"), nullable=False, server_default="autonomous"),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_agent_actions_created_at", "agent_actions", ["created_at"])
    op.create_index("ix_agent_actions_tool_name", "agent_actions", ["tool_name"])
    op.create_index("ix_agent_actions_session_id", "agent_actions", ["session_id"])
    op.create_index("ix_agent_actions_organization_id", "agent_actions", ["organization_id"])


def downgrade() -> None:
    op.drop_table("agent_actions")
    op.drop_table("log_records")
    op.drop_table("log_sessions")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS severitylevel")
    op.execute("DROP TYPE IF EXISTS logformat")
    op.execute("DROP TYPE IF EXISTS ingestionstatus")
    op.execute("DROP TYPE IF EXISTS autonomytier")
    op.execute("DROP TYPE IF EXISTS userrole")
