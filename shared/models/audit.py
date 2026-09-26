from sqlalchemy import Column, String, Float, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class AgentAction(Base):
    """
    Immutable audit record written for every autonomous or human-approved
    action the agent takes.  100% of high-impact actions must appear here.
    """

    __tablename__ = "agent_actions"

    # What tool triggered this action
    tool_name = Column(String(128), nullable=False, index=True)

    # Which service it concerns (nullable for global actions)
    service_id = Column(UUID(as_uuid=True), ForeignKey("monitored_services.id", ondelete="SET NULL"), nullable=True)

    # What triggered it — "scheduled_loop" | "alert_threshold" | "user_request"
    trigger = Column(String(128), nullable=False)

    # Agent confidence at time of action (0.0–1.0)
    confidence = Column(Float, nullable=True)

    # Autonomy tier used for this action
    autonomy_tier = Column(String(32), nullable=False)

    # Human who approved it (NULL if auto-executed under 'auto' tier)
    approver = Column(String(255), nullable=True)

    # Free-text description of what happened
    description = Column(Text, nullable=False)

    # Whether this action has been reversed (for reversible actions)
    reversed = Column(Boolean, nullable=False, default=False)
    reversed_by = Column(String(255), nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=False)
