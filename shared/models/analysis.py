"""
Phase 3 — Analysis & Correlation Layer SQLAlchemy models.

Tables:
  deduped_errors       — semantic-similarity grouped error records
  error_clusters       — DBSCAN embedding-based cluster definitions
  service_health_state — continuously-updated per-service health snapshot
  anomaly_events       — detected anomalies with NL explanations
  deployment_regressions — regression detections tied to deploy events
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


# ── Deduplicated Errors ───────────────────────────────────────────────────────

class DeduplicatedError(Base):
    """
    Semantic-similarity grouped error.

    Each row represents one distinct error group (not one log line).
    occurrence_count tracks how many raw log lines were deduplicated into it.
    first_seen / last_seen give temporal range.
    canonical_message is the representative log message chosen for the group.
    embedding stores the centroid vector for future similarity comparisons.
    """

    __tablename__ = "deduped_errors"

    service_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Hash fingerprint of the canonical message (for fast exact-match lookup)
    fingerprint = Column(String(64), nullable=False, index=True)

    canonical_message = Column(Text, nullable=False)
    severity = Column(String(16), nullable=False, default="ERROR")

    occurrence_count = Column(Integer, nullable=False, default=1)
    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False)

    # pgvector embedding centroid (average of all deduplicated messages)
    # Stored as JSON list to avoid a hard pgvector dependency at model-import time;
    # the migration creates a real vector column on the DB side.
    embedding = Column(JSON, nullable=True)   # list[float] len=1536

    # IDs of the raw log_records rows that were collapsed into this group
    source_record_ids = Column(JSON, nullable=True)   # list[str]

    # Cluster assignment (FK to error_clusters)
    cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("error_clusters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index("ix_deduped_service_fingerprint", "service_id", "fingerprint"),
        Index("ix_deduped_service_last_seen", "service_id", "last_seen"),
    )


# ── Error Clusters ────────────────────────────────────────────────────────────

class ErrorCluster(Base):
    """
    An embedding-based cluster of semantically-similar errors.

    Created/updated by the DBSCAN clustering pipeline.
    auto_label is an LLM-generated human-readable description of the cluster.
    confidence_score is the average intra-cluster cosine similarity (silhouette proxy).
    """

    __tablename__ = "error_clusters"

    service_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # DBSCAN assigns integer cluster labels; -1 = noise
    cluster_label = Column(Integer, nullable=False)

    # LLM-generated label describing the cluster
    auto_label = Column(String(512), nullable=True)

    # Average intra-cluster cosine similarity (0–1)
    confidence_score = Column(Float, nullable=False, default=0.0)

    # Number of unique deduped_errors assigned to this cluster
    member_count = Column(Integer, nullable=False, default=0)

    # Centroid vector (JSON list — same reasoning as DeduplicatedError.embedding)
    centroid_embedding = Column(JSON, nullable=True)   # list[float] len=1536

    # Whether the cluster is currently active (vs. dormant / resolved)
    is_active = Column(Boolean, nullable=False, default=True)

    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_cluster_service_label", "service_id", "cluster_label"),
    )


# ── Service Health State ──────────────────────────────────────────────────────

class ServiceHealthState(Base):
    """
    Continuously-updated, read-only per-service health state.

    Written by the analysis pipeline after every dedup/cluster pass.
    Backed by the service_baselines / error_clusters / dedup_events schema
    described in PRD §9.2 Failure Risk Board.

    health_score: 0–100, higher is healthier
    active_cluster_count: number of currently-active error clusters
    open_anomaly_count: unresolved anomalies
    top_cluster_label: the most-active cluster's auto-label
    """

    __tablename__ = "service_health_states"

    service_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_services.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one active row per service
        index=True,
    )

    # Composite health score (0–100; higher = healthier)
    health_score = Column(Float, nullable=False, default=100.0)

    # Baseline error rate from the last 28-day window
    baseline_error_rate = Column(Float, nullable=False, default=0.0)

    # Current period error rate
    current_error_rate = Column(Float, nullable=False, default=0.0)

    # Deviation from baseline (z-score)
    baseline_deviation_z = Column(Float, nullable=False, default=0.0)

    # Cluster counts
    active_cluster_count = Column(Integer, nullable=False, default=0)
    total_deduped_error_count = Column(Integer, nullable=False, default=0)

    # Open anomaly count
    open_anomaly_count = Column(Integer, nullable=False, default=0)

    # Summary label from the most-active cluster
    top_cluster_label = Column(String(512), nullable=True)

    # Latest risk tier from the forecasting loop
    latest_risk_tier = Column(String(16), nullable=False, default="normal")
    latest_risk_score = Column(Float, nullable=False, default=0.0)

    evaluated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_health_state_service", "service_id"),
    )


# ── Anomaly Events ────────────────────────────────────────────────────────────

class AnomalyEvent(Base):
    """
    A detected anomaly — statistical baseline deviation or new error type spike.

    anomaly_type: 'spike' | 'new_error_type' | 'service_silence' | 'cluster_drift'
    explanation: natural-language sentence surfaced into the Agent Feed.
    is_resolved: set to True when the anomaly clears.
    """

    __tablename__ = "anomaly_events"

    service_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("error_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )

    anomaly_type = Column(String(64), nullable=False)
    # Natural-language explanation for the Agent Feed
    explanation = Column(Text, nullable=False)

    # The statistical signal that triggered detection
    z_score = Column(Float, nullable=True)
    observed_value = Column(Float, nullable=True)
    baseline_mean = Column(Float, nullable=True)
    baseline_std = Column(Float, nullable=True)

    severity = Column(String(16), nullable=False, default="warning")   # warning | critical

    detected_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    is_resolved = Column(Boolean, nullable=False, default=False)

    # Extra machine-readable context
    context = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_anomaly_service_detected", "service_id", "detected_at"),
        Index("ix_anomaly_service_unresolved", "service_id", "is_resolved"),
    )


# ── Deployment Regressions ────────────────────────────────────────────────────

class DeploymentRegression(Base):
    """
    A regression detected by comparing two deployment versions.

    Automatically created when a new deployment event is received and the
    comparison tool detects a statistically significant increase in error rate
    or a new cluster appearing after the deploy.

    baseline_version / head_version — the two deployments compared.
    regression_type: 'error_rate_spike' | 'new_error_cluster' | 'cluster_size_jump'
    """

    __tablename__ = "deployment_regressions"

    service_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    baseline_version = Column(String(255), nullable=False)
    head_version = Column(String(255), nullable=False)

    regression_type = Column(String(64), nullable=False)
    explanation = Column(Text, nullable=False)

    # Quantitative evidence
    baseline_error_rate = Column(Float, nullable=True)
    head_error_rate = Column(Float, nullable=True)
    error_rate_delta = Column(Float, nullable=True)

    # Cluster that appeared or grew
    cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("error_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )

    confidence = Column(Float, nullable=True)   # 0.0–1.0

    detected_at = Column(DateTime(timezone=True), nullable=False)
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(String(255), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_regression_service_detected", "service_id", "detected_at"),
    )
