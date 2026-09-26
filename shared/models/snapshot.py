from sqlalchemy import Column, Float, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class RiskSnapshot(Base):
    """
    One complete risk-score cycle result for a service.
    Written at the end of every forecasting loop iteration.
    """

    __tablename__ = "risk_snapshots"

    service_id = Column(UUID(as_uuid=True), ForeignKey("monitored_services.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=False)

    # Component scores (0–100 each)
    velocity_score = Column(Float, nullable=False, default=0.0)    # 30 % weight
    similarity_score = Column(Float, nullable=False, default=0.0)  # 40 % weight
    baseline_score = Column(Float, nullable=False, default=0.0)    # 30 % weight

    # Weighted composite
    risk_score = Column(Float, nullable=False, default=0.0)        # 0–100

    # Human-readable tier derived from thresholds
    risk_tier = Column(String(16), nullable=False, default="normal")  # normal | warning | critical

    # Whether cloud AI was available for this cycle
    ai_assisted = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_snapshot_service_time", "service_id", "evaluated_at"),
    )
