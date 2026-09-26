from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class ErrorVelocityWindow(Base):
    """
    One 60-second (configurable) error-count sample for a service.
    Stores raw count + pre-computed first and second derivatives so the
    scoring layer can read them without recalculating.
    """

    __tablename__ = "error_velocity_windows"

    service_id = Column(UUID(as_uuid=True), ForeignKey("monitored_services.id", ondelete="CASCADE"), nullable=False, index=True)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)

    # Counts per severity level
    severity = Column(String(16), nullable=False)   # ERROR, CRITICAL, WARN, …
    error_count = Column(Integer, nullable=False, default=0)

    # Derivatives (None until at least 2 windows exist)
    first_derivative = Column(Float, nullable=True)   # Δcount / Δt
    second_derivative = Column(Float, nullable=True)  # ΔΔcount / Δt²

    __table_args__ = (
        Index("ix_velocity_service_window", "service_id", "window_start"),
    )
