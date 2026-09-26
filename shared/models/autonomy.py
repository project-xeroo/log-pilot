from sqlalchemy import Column, String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class AutonomyPolicy(Base):
    """
    Per-tool, per-environment autonomy tier configuration.
    An organisation can set each tool to observe | propose | auto per environment.
    Any tool not found here defaults to 'propose'.
    """

    __tablename__ = "autonomy_policy"

    service_id = Column(UUID(as_uuid=True), ForeignKey("monitored_services.id", ondelete="CASCADE"), nullable=True)
    # NULL service_id means the policy applies to ALL services

    tool_name = Column(String(128), nullable=False)
    # e.g. "proactive_forecasting", "pre_mortem_report", "recommended_action"

    environment = Column(String(64), nullable=False, default="production")

    autonomy_tier = Column(String(32), nullable=False, default="propose")
    # observe  — surface information only, no actions
    # propose  — generate action + require human approval before execution
    # auto     — execute directly and log for audit (opt-in, highest trust)

    __table_args__ = (
        UniqueConstraint("tool_name", "environment", "service_id", name="uq_policy_tool_env_service"),
    )
