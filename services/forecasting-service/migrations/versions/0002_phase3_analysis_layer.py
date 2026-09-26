"""Phase 3 — Analysis & Correlation Layer tables

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── error_clusters (must exist before deduped_errors for FK) ─────────────
    op.create_table(
        "error_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_label", sa.Integer, nullable=False),
        sa.Column("auto_label", sa.String(512), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("member_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("centroid_embedding", postgresql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cluster_service_label", "error_clusters", ["service_id", "cluster_label"])

    # ── deduped_errors ────────────────────────────────────────────────────────
    op.create_table(
        "deduped_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("canonical_message", sa.Text, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="ERROR"),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("embedding", postgresql.JSON, nullable=True),
        sa.Column("source_record_ids", postgresql.JSON, nullable=True),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["error_clusters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deduped_service_fingerprint", "deduped_errors", ["service_id", "fingerprint"])
    op.create_index("ix_deduped_service_last_seen", "deduped_errors", ["service_id", "last_seen"])

    # ── service_health_states ──────────────────────────────────────────────────
    op.create_table(
        "service_health_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("health_score", sa.Float, nullable=False, server_default="100"),
        sa.Column("baseline_error_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("current_error_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("baseline_deviation_z", sa.Float, nullable=False, server_default="0"),
        sa.Column("active_cluster_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_deduped_error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("open_anomaly_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("top_cluster_label", sa.String(512), nullable=True),
        sa.Column("latest_risk_tier", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("latest_risk_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", name="uq_health_state_service"),
    )
    op.create_index("ix_health_state_service", "service_health_states", ["service_id"])

    # ── anomaly_events ────────────────────────────────────────────────────────
    op.create_table(
        "anomaly_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("anomaly_type", sa.String(64), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("z_score", sa.Float, nullable=True),
        sa.Column("observed_value", sa.Float, nullable=True),
        sa.Column("baseline_mean", sa.Float, nullable=True),
        sa.Column("baseline_std", sa.Float, nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="warning"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("context", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["error_clusters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomaly_service_detected", "anomaly_events", ["service_id", "detected_at"])
    op.create_index("ix_anomaly_service_unresolved", "anomaly_events", ["service_id", "is_resolved"])

    # ── deployment_regressions ────────────────────────────────────────────────
    op.create_table(
        "deployment_regressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_version", sa.String(255), nullable=False),
        sa.Column("head_version", sa.String(255), nullable=False),
        sa.Column("regression_type", sa.String(64), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("baseline_error_rate", sa.Float, nullable=True),
        sa.Column("head_error_rate", sa.Float, nullable=True),
        sa.Column("error_rate_delta", sa.Float, nullable=True),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("acknowledged_by", sa.String(255), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["monitored_services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["error_clusters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regression_service_detected", "deployment_regressions", ["service_id", "detected_at"])


def downgrade() -> None:
    op.drop_table("deployment_regressions")
    op.drop_index("ix_anomaly_service_unresolved")
    op.drop_index("ix_anomaly_service_detected")
    op.drop_table("anomaly_events")
    op.drop_index("ix_health_state_service")
    op.drop_table("service_health_states")
    op.drop_index("ix_deduped_service_last_seen")
    op.drop_index("ix_deduped_service_fingerprint")
    op.drop_table("deduped_errors")
    op.drop_index("ix_cluster_service_label")
    op.drop_table("error_clusters")
