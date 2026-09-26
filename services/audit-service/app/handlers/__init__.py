from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.exporters import report_to_markdown, report_to_pdf_bytes

router = APIRouter(prefix="/export", tags=["export"])
logger = logging.getLogger("audit.handlers")


class ReportPayload(BaseModel):
    """Mirrors the ReportOut shape from the API gateway."""
    id: str
    title: str
    status: str
    summary: str | None = None
    timeline: str | None = None
    affected_services: list[str] | None = None
    impact_analysis: str | None = None
    root_cause: str | None = None
    resolution: str | None = None
    preventive_actions: str | None = None
    incident_id: str | None = None
    severity: str | None = None
    started_at: str | None = None
    resolved_at: str | None = None
    ttd_seconds: float | None = None
    ttr_seconds: float | None = None
    generation_model: str | None = None
    generation_duration_ms: float | None = None
    author_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@router.post("/markdown")
def export_markdown(payload: ReportPayload):
    text = report_to_markdown(payload.model_dump())
    filename = f"incident-report-{payload.id[:8]}.md"
    return Response(
        content=text,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/pdf")
def export_pdf(payload: ReportPayload):
    pdf_bytes = report_to_pdf_bytes(payload.model_dump())
    filename = f"incident-report-{payload.id[:8]}.pdf"
    # If WeasyPrint returned HTML fallback, detect content type
    if pdf_bytes[:4] == b"<!DO":
        return Response(
            content=pdf_bytes,
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}.html"'},
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
