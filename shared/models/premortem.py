from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class PreMortemReport(Base):
    """
    A pre-mortem report drafted automatically by the AI service when risk
    crosses the critical threshold. Requires human sign-off before it is
    considered finalised.
    """

    __tablename__ = "pre_mortem_reports"

    service_id = Column(UUID(as_uuid=True), ForeignKey("monitored_services.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_id = Column(UUID(as_uuid=True), ForeignKey("pre_incident_alerts.id", ondelete="SET NULL"), nullable=True)

    # Report content
    title = Column(String(512), nullable=False)
    body_markdown = Column(Text, nullable=False)   # Full Markdown body

    # Status lifecycle
    status = Column(String(32), nullable=False, default="draft")
    # draft | pending_review | approved | rejected

    # Human reviewer
    reviewed_by = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_notes = Column(Text, nullable=True)

    # Whether the final approved version has been exported
    exported = Column(Boolean, nullable=False, default=False)
    export_format = Column(String(16), nullable=True)  # pdf | markdown
