from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_permission
from app.config import settings
from shared.models import (
    IncidentReport,
    Permission,
    ReportStatus,
)
from shared.utils import get_session

router = APIRouter(prefix="/reports", tags=["reports"])

DBSession = Annotated[Session, Depends(get_session)]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ReportSectionUpdate(BaseModel):
    summary: str | None = None
    timeline: str | None = None
    affected_services: list[str] | None = None
    impact_analysis: str | None = None
    root_cause: str | None = None
    resolution: str | None = None
    preventive_actions: str | None = None
    title: str | None = None
    status: ReportStatus | None = None
    severity: str | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None


class GenerateReportRequest(BaseModel):
    incident_id: str
    title: str
    severity: str | None = "medium"
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    context_logs: list[str] | None = None     # up to N relevant log lines
    affected_services: list[str] | None = None


class ReportOut(BaseModel):
    id: str
    title: str
    status: str
    summary: str | None
    timeline: str | None
    affected_services: list[str] | None
    impact_analysis: str | None
    root_cause: str | None
    resolution: str | None
    preventive_actions: str | None
    incident_id: str | None
    severity: str | None
    started_at: datetime | None
    resolved_at: datetime | None
    ttd_seconds: float | None
    ttr_seconds: float | None
    generation_model: str | None
    generation_duration_ms: float | None
    author_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=ReportOut,
    status_code=202,
    dependencies=[require_permission(Permission.report_create)],
)
def generate_report(
    body: GenerateReportRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    """Ask the AI service to draft a full incident report and persist it."""
    try:
        resp = httpx.post(
            f"{settings.ai_service_url}/reports/generate",
            json=body.model_dump(mode="json"),
            timeout=120.0,
        )
        resp.raise_for_status()
        draft: dict[str, Any] = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}") from exc

    report = IncidentReport(
        title=body.title,
        incident_id=body.incident_id,
        severity=body.severity,
        started_at=body.started_at,
        resolved_at=body.resolved_at,
        affected_services=body.affected_services or draft.get("affected_services"),
        author_id=current_user.id,
        summary=draft.get("summary"),
        timeline=draft.get("timeline"),
        impact_analysis=draft.get("impact_analysis"),
        root_cause=draft.get("root_cause"),
        resolution=draft.get("resolution"),
        preventive_actions=draft.get("preventive_actions"),
        generation_model=draft.get("model"),
        generation_prompt_version=draft.get("prompt_version"),
        generation_duration_ms=draft.get("duration_ms"),
    )
    session.add(report)
    session.flush()
    return ReportOut.model_validate(report)


@router.get(
    "",
    dependencies=[require_permission(Permission.report_read)],
)
def list_reports(
    session: DBSession,
    status: ReportStatus | None = None,
    severity: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = session.query(IncidentReport)
    if status:
        q = q.filter(IncidentReport.status == status)
    if severity:
        q = q.filter(IncidentReport.severity == severity)
    q = q.order_by(IncidentReport.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [ReportOut.model_validate(r) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{report_id}",
    response_model=ReportOut,
    dependencies=[require_permission(Permission.report_read)],
)
def get_report(report_id: str, session: DBSession):
    report = session.get(IncidentReport, uuid.UUID(report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportOut.model_validate(report)


@router.patch(
    "/{report_id}",
    response_model=ReportOut,
    dependencies=[require_permission(Permission.report_update)],
)
def update_report(report_id: str, body: ReportSectionUpdate, session: DBSession):
    report = session.get(IncidentReport, uuid.UUID(report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(report, field, value)
    session.flush()
    return ReportOut.model_validate(report)


@router.delete(
    "/{report_id}",
    status_code=204,
    dependencies=[require_permission(Permission.report_delete)],
)
def delete_report(report_id: str, session: DBSession):
    report = session.get(IncidentReport, uuid.UUID(report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    session.delete(report)


@router.get(
    "/{report_id}/export/{format}",
    dependencies=[require_permission(Permission.report_export)],
)
def export_report(report_id: str, format: str, session: DBSession):
    """Delegate export to the audit service; returns the raw bytes or a URL."""
    if format not in ("pdf", "markdown"):
        raise HTTPException(status_code=400, detail="format must be 'pdf' or 'markdown'")
    report = session.get(IncidentReport, uuid.UUID(report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        resp = httpx.post(
            f"{settings.audit_service_url}/export/{format}",
            json=ReportOut.model_validate(report).model_dump(mode="json"),
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Audit service error: {exc}") from exc

    # Mark report as exported
    report.status = ReportStatus.exported
    session.flush()
    return resp.json()
