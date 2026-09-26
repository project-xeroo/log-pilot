import enum

from sqlalchemy import Column, String, Float, Text, DateTime, ForeignKey, Boolean, Index, func
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class AutonomyTier(str, enum.Enum):
    """Tier labels written by the ingestion pipeline (PRD §8.2).

    The forecasting loop writes its own policy tiers (observe | propose | auto),
    so the column is a plain string rather than a Postgres enum.
    """

    READ_ONLY = "read_only"
    PROPOSE_ONLY = "propose_only"
    AUTONOMOUS = "autonomous"


class AgentAction(Base):
    """
    Immutable audit record written for every autonomous or human-approved
    action the agent takes.  100% of high-impact actions must appear here.
    """

    __tablename__ = "agent_actions"

    # What tool triggered this action
    tool_name = Column(String(128), nullable=False)

    # Which service it concerns (nullable for global actions)
    service_id = Column(UUID(as_uuid=True), ForeignKey("monitored_services.id", ondelete="SET NULL"), nullable=True)

    # What triggered it — "scheduled_loop" | "alert_threshold" | "user_request" | "upload" | "api"
    trigger = Column(String(128), nullable=False)

    # Agent confidence at time of action (0.0–1.0)
    confidence = Column(Float, nullable=True)

    # Autonomy tier used for this action
    autonomy_tier = Column(String(32), nullable=False)

    # Human who approved it (NULL if auto-executed under 'auto' tier)
    approver = Column(String(255), nullable=True)
    # User who initiated it (NULL = autonomous agent)
    actor_user_id = Column(UUID(as_uuid=True), nullable=True)

    # Free-text description of what happened
    description = Column(Text, nullable=True)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)

    # completed | failed | proposed
    status = Column(String(32), nullable=False, default="completed")
    error = Column(Text, nullable=True)

    # Upload session this action processed (ingestion pipeline)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True)

    # Whether this action has been reversed (for reversible actions)
    reversed = Column(Boolean, nullable=False, default=False)
    reversed_by = Column(String(255), nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_agent_actions_tool_name", "tool_name"),
        Index("ix_agent_actions_executed_at", "executed_at"),
        Index("ix_agent_actions_session_id", "session_id"),
        Index("ix_agent_actions_organization_id", "organization_id"),
    )
