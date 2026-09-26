from sqlalchemy import Column, String, Boolean, Text
from .base import Base


class MonitoredService(Base):
    """A service whose logs the agent is watching."""

    __tablename__ = "monitored_services"

    name = Column(String(255), nullable=False, unique=True, index=True)
    environment = Column(String(64), nullable=False, default="production")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # Forecasting loop interval in seconds (overrides the global default)
    loop_interval_seconds = Column(String(16), nullable=False, default="60")
