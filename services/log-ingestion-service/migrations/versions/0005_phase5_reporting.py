"""
Phase 5 — Reporting & feedback loop.

Creates:
  - incident_reports      — agent-drafted incident reports (human sign-off)
  - incident_outcomes     — outcome labels feeding the forecasting feedback loop
  - forecast_weights      — persisted per-indicator weights learned from outcomes
  - deployment_snapshots  — deploy events for the Deployment Comparison screen
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_phase5_reporting"
down_revision = "0004_phase3_analysis_layer"
branch_labels = None
depends_on = None

REPORT_STATUS = ("draft", "review", "approved", "exported")
OUTCOME_VERDICT = ("true_positive", "false_positive", "true_negative", "false_negative")


def _create_enum(name: str, *values: str) -> None:
    labels = ", ".join(f"'{v}'" for v in values)
    op.execute(f"""
        DO $$ BEGIN
            CREATE TYPE {name} AS ENUM ({labels});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    _create_enum("reportstatus", *REPORT_STATUS)
    _create_enum("outcomeverdict", *OUTCOME_VERDICT)

    # ── incident_reports ─────────────────────────────────────────────────────
    op.create_table(
        "incident_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_timestamps(),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("status", postgresql.ENUM(*REPORT_STATUS, name="reportstatus", create_type=False), nullable=False, server_default="draft"),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("timeline", sa.Text, nullable=True),
        sa.Column("affected_services", sa.JSON, nullable=True),
        sa.Column("impact_analysis", sa.Text, nullable=True),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("resolution", sa.Text, nullable=True),
        sa.Column("preventive_actions", sa.Text, nullable=True),
        sa.Column("incident_id", sa.String(255), nullable=True),
        sa.Column("severity", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ttd_seconds", sa.Float, nullable=True),
        sa.Column("ttr_seconds", sa.Float, nullable=True),
        sa.Column("generation_model", sa.String(100), nullable=True),
        sa.Column("generation_prompt_version", sa.String(50), nullable=True),
        sa.Column("generation_duration_ms", sa.Float, nullable=True),
    )
    op.create_index("ix_incident_reports_status", "incident_reports", ["status"])
    op.create_index("ix_incident_reports_created_at", "incident_reports", ["created_at"])

    # ── incident_outcomes ────────────────────────────────────────────────────
    op.create_table(
        "incident_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_timestamps(),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incident_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pre_incident_alerts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("incident_id", sa.String(255), nullable=False),
        sa.Column("verdict", postgresql.ENUM(*OUTCOME_VERDICT, name="outcomeverdict", create_type=False), nullable=False),
        sa.Column("rca_accurate", sa.Boolean, nullable=True),
        sa.Column("forecast_accurate", sa.Boolean, nullable=True),
        sa.Column("time_to_detect_seconds", sa.Float, nullable=True),
        sa.Column("time_to_resolve_seconds", sa.Float, nullable=True),
        sa.Column("action_taken", sa.Text, nullable=True),
        sa.Column("fired_indicators", sa.JSON, nullable=True),
        sa.Column("forecast_score_at_incident", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_incident_outcomes_incident_id", "incident_outcomes", ["incident_id"])
    op.create_index("ix_incident_outcomes_alert_id", "incident_outcomes", ["alert_id"])

    # ── forecast_weights ─────────────────────────────────────────────────────
    op.create_table(
        "forecast_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_timestamps(),
        sa.Column("indicator_name", sa.String(255), nullable=False, unique=True),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("true_positive_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("false_positive_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("false_negative_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_fired", sa.Integer, nullable=False, server_default="0"),
        sa.Column("precision", sa.Float, nullable=False, server_default="0"),
        sa.Column("recall", sa.Float, nullable=False, server_default="0"),
    )

    # ── deployment_snapshots ─────────────────────────────────────────────────
    op.create_table(
        "deployment_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_timestamps(),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(100), nullable=False, server_default="production"),
        sa.Column("version", sa.String(255), nullable=False),
        sa.Column("deployed_by", sa.String(255), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_snapshot", sa.JSON, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
    )
    op.create_index("ix_deployment_snapshots_service_env", "deployment_snapshots", ["service_name", "environment", "deployed_at"])


def downgrade() -> None:
    op.drop_table("deployment_snapshots")
    op.drop_table("forecast_weights")
    op.drop_table("incident_outcomes")
    op.drop_table("incident_reports")
    op.execute("DROP TYPE IF EXISTS outcomeverdict")
    op.execute("DROP TYPE IF EXISTS reportstatus")
