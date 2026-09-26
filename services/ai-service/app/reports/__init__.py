<<<<<<< HEAD
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.reports.generator import generate_incident_report

router = APIRouter(prefix="/reports", tags=["reports"])
logger = logging.getLogger("ai-service.reports")


class GenerateRequest(BaseModel):
    incident_id: str
    title: str
    severity: str | None = "medium"
    started_at: str | None = None
    resolved_at: str | None = None
    context_logs: list[str] | None = None
    affected_services: list[str] | None = None


@router.post("/generate")
def generate(body: GenerateRequest) -> dict[str, Any]:
    """Generate a structured incident report draft using the LLM."""
    logger.info("Generating report for incident %s", body.incident_id)
    try:
        return generate_incident_report(
            incident_id=body.incident_id,
            title=body.title,
            severity=body.severity or "medium",
            started_at=body.started_at,
            resolved_at=body.resolved_at,
            affected_services=body.affected_services,
            context_logs=body.context_logs,
        )
    except Exception as exc:
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
=======
from .generator import enrich_report_with_ai, approve_report, export_report_markdown, export_report_pdf

__all__ = ["enrich_report_with_ai", "approve_report", "export_report_markdown", "export_report_pdf"]
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
