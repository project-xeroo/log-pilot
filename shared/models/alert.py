from sqlalchemy import Column, Float, String, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class PreIncidentAlert(Base):
    """
    An alert surfaced by the forecasting loop when risk crosses a threshold.
    Contains natural-language explanation, confidence, matched pattern, and
    recommended actions (propose-only by default).
    """

    __tablename__ = "pre_incident_alerts"

    service_id = Column(UUID(as_uuid=True), ForeignKey("monitored_services.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("risk_snapshots.id", ondelete="SET NULL"), nullable=True)

    risk_score = Column(Float, nullable=False)
    risk_tier = Column(String(16), nullable=False)  # warning | critical

    # AI-generated explanation
    explanation = Column(Text, nullable=False)
    matched_pattern = Column(String(512), nullable=True)
    confidence = Column(Float, nullable=True)          # 0.0 – 1.0

    # Historical precedent (similar past alert IDs)
    similar_past_event_ids = Column(JSON, nullable=True)  # list[str]

    # Recommended actions list  [{"action": "...", "priority": 1}]
    recommended_actions = Column(JSON, nullable=True)

    # Alert lifecycle
    status = Column(String(32), nullable=False, default="open")
    # open | acknowledged | approved | dismissed | resolved

    # Who handled it and when
    handled_by = Column(String(255), nullable=True)
    handled_at = Column(DateTime(timezone=True), nullable=True)

    # SRE edit to a recommended action before approval
    edited_action = Column(Text, nullable=True)

    alerted_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_alert_service_status", "service_id", "status"),
    )
