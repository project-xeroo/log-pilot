"""initial schema — all LogPilot forecasting tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── monitored_services ────────────────────────────────────────────────────
    op.create_table(
        "monitored_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(64), nullable=False, server_default="production"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("loop_interval_seconds", sa.String(16), nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_monitored_services_name", "monitored_services", ["name"])

    # ── error_velocity_windows ────────────────────────────────────────────────
    op.create_table(
        "error_velocity_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_derivative", sa.Float, nullable=True),
        sa.Column("second_derivative", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_velocity_service_window", "error_velocity_windows", ["service_id", "window_start"])

    # ── risk_snapshots ────────────────────────────────────────────────────────
    op.create_table(
        "risk_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("velocity_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("similarity_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("baseline_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("risk_tier", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("ai_assisted", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_snapshot_service_time", "risk_snapshots", ["service_id", "evaluated_at"])

    # ── pre_incident_alerts ───────────────────────────────────────────────────
    op.create_table(
        "pre_incident_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_score", sa.Float, nullable=False),
        sa.Column("risk_tier", sa.String(16), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("matched_pattern", sa.String(512), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("similar_past_event_ids", postgresql.JSON, nullable=True),
        sa.Column("recommended_actions", postgresql.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("handled_by", sa.String(255), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_action", sa.Text, nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["risk_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_service_status", "pre_incident_alerts", ["service_id", "status"])

    # ── pre_mortem_reports ────────────────────────────────────────────────────
    op.create_table(
        "pre_mortem_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body_markdown", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text, nullable=True),
        sa.Column("exported", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("export_format", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["alert_id"], ["pre_incident_alerts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── autonomy_policy ───────────────────────────────────────────────────────
    op.create_table(
        "autonomy_policy",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(64), nullable=False, server_default="production"),
        sa.Column("autonomy_tier", sa.String(32), nullable=False, server_default="propose"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tool_name", "environment", "service_id", name="uq_policy_tool_env_service"),
    )

    # ── agent_actions ─────────────────────────────────────────────────────────
    op.create_table(
        "agent_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger", sa.String(128), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("autonomy_tier", sa.String(32), nullable=False),
        sa.Column("approver", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("reversed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("reversed_by", sa.String(255), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_actions_tool", "agent_actions", ["tool_name"])

    # ── leading_indicator_embeddings (pgvector) ───────────────────────────────
    # Stores historical failure embeddings for similarity matching
    op.execute("""
        CREATE TABLE leading_indicator_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            service_id UUID REFERENCES monitored_services(id) ON DELETE CASCADE,
            alert_id UUID REFERENCES pre_incident_alerts(id) ON DELETE SET NULL,
            embedding vector(1536) NOT NULL,
            label TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_embedding_service
        ON leading_indicator_embeddings (service_id)
    """)
    op.execute("""
        CREATE INDEX ix_embedding_hnsw
        ON leading_indicator_embeddings
        USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leading_indicator_embeddings CASCADE")
    op.drop_table("agent_actions")
    op.drop_table("autonomy_policy")
    op.drop_table("pre_mortem_reports")
    op.drop_table("pre_incident_alerts")
    op.drop_table("risk_snapshots")
    op.drop_table("error_velocity_windows")
    op.drop_table("monitored_services")
