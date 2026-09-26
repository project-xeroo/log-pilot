"""
Phase 2 schema migration.

Creates:
  - chat_sessions     — one row per conversation thread
  - chat_messages     — one row per assistant response (user questions stored inline)
  - chat_ratings      — thumbs up/down per message (PRD: > 80% helpful target)
  - agent_feed        — chronological stream of what the agent has noticed/said/drafted
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_phase2_chat_feed"
down_revision = "0002_forecasting_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── chat_sessions ────────────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),   # auto-generated from first question
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_chat_sessions_updated_at", "chat_sessions", ["updated_at"])

    # ── chat_messages ─────────────────────────────────────────────────────────
    # Stores both user questions (role='user') and assistant answers (role='assistant')
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),            # 'user' | 'assistant'
        sa.Column("content", sa.Text, nullable=False),               # message text
        sa.Column("cited_record_ids", postgresql.ARRAY(sa.BigInteger), nullable=True),
        sa.Column("context_record_count", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Float, nullable=True),            # assistant turns only
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])

    # ── chat_ratings ──────────────────────────────────────────────────────────
    op.create_table(
        "chat_ratings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("helpful", sa.Boolean, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
    )
    op.create_index("ix_chat_ratings_message_id", "chat_ratings", ["message_id"])

    # ── agent_feed ────────────────────────────────────────────────────────────
    # Chronological stream of everything the agent has noticed, said, or drafted.
    # Each row is one "card" in the Agent Feed screen.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE feedentrytype AS ENUM (
                'anomaly_detected',
                'risk_score_updated',
                'chat_answer',
                'ingestion_completed',
                'alert_fired',
                'report_drafted',
                'agent_observation'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "agent_feed",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "entry_type",
            postgresql.ENUM(
                "anomaly_detected", "risk_score_updated", "chat_answer",
                "ingestion_completed", "alert_fired", "report_drafted", "agent_observation",
                name="feedentrytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("service_name", sa.String(256), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),         # Short headline
        sa.Column("body", sa.Text, nullable=True),                   # Longer explanation
        sa.Column("severity", sa.String(32), nullable=True),         # If applicable
        sa.Column("risk_score", sa.Float, nullable=True),            # 0–100 for risk events
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_chat_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),      # Arbitrary extra data
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_agent_feed_created_at", "agent_feed", ["created_at"])
    op.create_index("ix_agent_feed_entry_type", "agent_feed", ["entry_type"])
    op.create_index("ix_agent_feed_service_name", "agent_feed", ["service_name"])
    op.create_index("ix_agent_feed_organization_id", "agent_feed", ["organization_id"])


def downgrade() -> None:
    op.drop_table("agent_feed")
    op.execute("DROP TYPE IF EXISTS feedentrytype")
    op.drop_table("chat_ratings")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
