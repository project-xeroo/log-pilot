"""
Pre-mortem report generator.

Enhances the draft produced by the forecasting loop's premortem_trigger
with AI-generated root-cause analysis and narrative when a real provider
is configured. Falls back gracefully to the template body if AI is
unavailable.

Also handles:
- PDF export (via weasyprint, optional dependency)
- Markdown export (always available)
- Sign-off endpoint logic (status transition: draft → approved)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import PreMortemReport, PreIncidentAlert, MonitoredService
from app.providers import get_provider

logger = logging.getLogger(__name__)


_REPORT_PROMPT_TEMPLATE = """You are a senior SRE writing a pre-mortem report.
Service: {service_name}
Environment: {environment}
Risk score: {risk_score}/100 (tier: {risk_tier})
Matched pattern: {matched_pattern}
Agent explanation: {explanation}
Recommended actions: {actions}

Write a concise pre-mortem in markdown with sections:
1. Executive Summary
2. Root Cause Hypothesis
3. Contributing Factors
4. Impact Assessment
5. Recommended Remediation Steps
6. Prevention Measures

Be specific and evidence-based. Do not speculate beyond the signals provided."""


async def enrich_report_with_ai(
    db: AsyncSession,
    report_id: uuid.UUID,
) -> PreMortemReport:
    """
    Fetch an existing draft pre-mortem report, call the AI provider to
    enrich the body with deeper analysis, and update the record in place.
    Falls back to the existing template body if AI fails.
    """
    result = await db.execute(select(PreMortemReport).where(PreMortemReport.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise ValueError(f"Report {report_id} not found")

    alert_result = await db.execute(
        select(PreIncidentAlert).where(PreIncidentAlert.id == report.alert_id)
    )
    alert = alert_result.scalar_one_or_none()

    service_result = await db.execute(
        select(MonitoredService).where(MonitoredService.id == report.service_id)
    )
    service = service_result.scalar_one_or_none()

    if not alert or not service:
        return report  # nothing to enrich

    actions_text = ""
    if alert.recommended_actions:
        actions_text = "; ".join(a["action"] for a in alert.recommended_actions)

    prompt = _REPORT_PROMPT_TEMPLATE.format(
        service_name=service.name,
        environment=service.environment,
        risk_score=alert.risk_score,
        risk_tier=alert.risk_tier,
        matched_pattern=alert.matched_pattern or "unknown",
        explanation=alert.explanation,
        actions=actions_text or "none",
    )

    try:
        provider = get_provider()
        ai_response = await provider.complete(prompt, max_tokens=2048)
        report.body_markdown = ai_response.content
        await db.flush()
        logger.info("Pre-mortem report %s enriched by AI (%s)", report_id, ai_response.model)
    except Exception as exc:
        logger.warning("AI enrichment failed for report %s: %s — keeping template body", report_id, exc)

    return report


async def approve_report(
    db: AsyncSession,
    report_id: uuid.UUID,
    reviewer: str,
    notes: str | None = None,
) -> PreMortemReport:
    """
    Transition a draft/pending_review report to 'approved'.
    Records reviewer name and timestamp.
    """
    result = await db.execute(select(PreMortemReport).where(PreMortemReport.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise ValueError(f"Report {report_id} not found")
    if report.status not in ("draft", "pending_review"):
        raise ValueError(f"Report is already '{report.status}' — cannot approve")

    report.status = "approved"
    report.reviewed_by = reviewer
    report.reviewed_at = datetime.now(timezone.utc)
    report.reviewer_notes = notes
    await db.flush()
    return report


async def export_report_markdown(report: PreMortemReport) -> str:
    """Return the report body as plain Markdown string."""
    return report.body_markdown


async def export_report_pdf(report: PreMortemReport) -> bytes:
    """
    Convert the Markdown body to PDF using weasyprint.
    Returns raw PDF bytes.  Raises ImportError if weasyprint is not installed.
    """
    try:
        import markdown as md
        from weasyprint import HTML
    except ImportError as exc:
        raise ImportError(
            "PDF export requires 'markdown' and 'weasyprint'. "
            "Install them with: pip install markdown weasyprint"
        ) from exc

    html_body = md.markdown(report.body_markdown, extensions=["tables"])
    full_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; max-width: 800px; margin: 40px auto; font-size: 13px; }}
  h1, h2, h3 {{ color: #1f2328; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 6px 10px; text-align: left; }}
  th {{ background: #f7f8fa; }}
  code {{ background: #f7f8fa; padding: 2px 4px; border-radius: 3px; }}
</style>
</head><body>{html_body}</body></html>"""

    return HTML(string=full_html).write_pdf()
