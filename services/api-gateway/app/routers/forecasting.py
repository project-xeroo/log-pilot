"""
Forecasting router — all risk, alert, approval, and pre-mortem endpoints.

Endpoints:
  GET  /forecasting/risk/{service_id}          — latest risk snapshot
  GET  /forecasting/risk/{service_id}/history  — historical snapshots
  GET  /forecasting/alerts                     — all open alerts (approvals queue)
  GET  /forecasting/alerts/{alert_id}          — single alert detail
  POST /forecasting/alerts/{alert_id}/approve  — SRE approves a recommended action
  POST /forecasting/alerts/{alert_id}/edit     — SRE edits a recommended action before approval
  POST /forecasting/alerts/{alert_id}/dismiss  — SRE dismisses an alert
  GET  /forecasting/reports                    — list pre-mortem reports
  GET  /forecasting/reports/{report_id}        — single report
  POST /forecasting/reports/{report_id}/approve   — sign off a pre-mortem
  GET  /forecasting/reports/{report_id}/export    — download as PDF or Markdown
  GET  /forecasting/policy                    — list autonomy policies
  PUT  /forecasting/policy/{policy_id}        — update autonomy tier (admin only)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_db
from shared.models import (
    RiskSnapshot,
    PreIncidentAlert,
    PreMortemReport,
    AutonomyPolicy,
    AgentAction,
    MonitoredService,
)
from app.auth.jwt_auth import AnyAuthenticated, SREOrAdmin, AdminOnly, TokenPayload

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RiskSnapshotOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    evaluated_at: datetime
    velocity_score: float
    similarity_score: float
    baseline_score: float
    risk_score: float
    risk_tier: str
    ai_assisted: bool
    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    snapshot_id: uuid.UUID | None
    risk_score: float
    risk_tier: str
    explanation: str
    matched_pattern: str | None
    confidence: float | None
    similar_past_event_ids: list | None
    recommended_actions: list | None
    status: str
    handled_by: str | None
    handled_at: datetime | None
    edited_action: str | None
    alerted_at: datetime
    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    alert_id: uuid.UUID | None
    title: str
    body_markdown: str
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    reviewer_notes: str | None
    exported: bool
    export_format: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class PolicyOut(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID | None
    tool_name: str
    environment: str
    autonomy_tier: str
    model_config = {"from_attributes": True}


class ApproveAlertRequest(BaseModel):
    approved_by: str
    notes: str | None = None


class EditAlertRequest(BaseModel):
    edited_action: str
    edited_by: str


class DismissAlertRequest(BaseModel):
    dismissed_by: str
    reason: str | None = None


class ApproveReportRequest(BaseModel):
    reviewed_by: str
    notes: str | None = None


class UpdatePolicyRequest(BaseModel):
    autonomy_tier: Literal["observe", "propose", "auto"]


# ── Risk snapshots ────────────────────────────────────────────────────────────

@router.get("/risk/{service_id}", response_model=RiskSnapshotOut, dependencies=[Depends(AnyAuthenticated)])
async def get_latest_risk(service_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return the most-recent risk snapshot for a service."""
    stmt = (
        select(RiskSnapshot)
        .where(RiskSnapshot.service_id == service_id)
        .order_by(desc(RiskSnapshot.evaluated_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No risk data found for this service")
    return snapshot


@router.get("/risk/{service_id}/history", response_model=list[RiskSnapshotOut], dependencies=[Depends(AnyAuthenticated)])
async def get_risk_history(
    service_id: uuid.UUID,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(RiskSnapshot)
        .where(RiskSnapshot.service_id == service_id)
        .order_by(desc(RiskSnapshot.evaluated_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Alerts & approvals queue ──────────────────────────────────────────────────

@router.get("/alerts", response_model=list[AlertOut], dependencies=[Depends(AnyAuthenticated)])
async def list_alerts(
    status: str | None = None,
    service_id: uuid.UUID | None = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return all alerts (open by default) — the SRE approvals queue."""
    stmt = select(PreIncidentAlert).order_by(desc(PreIncidentAlert.alerted_at))
    if status:
        stmt = stmt.where(PreIncidentAlert.status == status)
    else:
        stmt = stmt.where(PreIncidentAlert.status == "open")
    if service_id:
        stmt = stmt.where(PreIncidentAlert.service_id == service_id)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/alerts/{alert_id}", response_model=AlertOut, dependencies=[Depends(AnyAuthenticated)])
async def get_alert(alert_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PreIncidentAlert).where(PreIncidentAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/alerts/{alert_id}/approve", response_model=AlertOut)
async def approve_alert(
    alert_id: uuid.UUID,
    body: ApproveAlertRequest,
    user: TokenPayload = Depends(SREOrAdmin),
    db: AsyncSession = Depends(get_db),
):
    """
    SRE or Admin approves a recommended action from a propose-only alert.
    Transitions status: open → approved and writes an audit record.
    """
    result = await db.execute(select(PreIncidentAlert).where(PreIncidentAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status != "open":
        raise HTTPException(status_code=409, detail=f"Alert is already '{alert.status}'")

    alert.status = "approved"
    alert.handled_by = body.approved_by
    alert.handled_at = datetime.now(timezone.utc)

    # Write audit record
    action = AgentAction(
        id=uuid.uuid4(),
        tool_name="proactive_forecasting",
        service_id=alert.service_id,
        trigger="user_request",
        autonomy_tier="propose",
        approver=body.approved_by,
        description=f"Alert {alert_id} approved by {body.approved_by}. Notes: {body.notes or 'none'}",
        executed_at=datetime.now(timezone.utc),
    )
    db.add(action)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/edit", response_model=AlertOut)
async def edit_alert_action(
    alert_id: uuid.UUID,
    body: EditAlertRequest,
    user: TokenPayload = Depends(SREOrAdmin),
    db: AsyncSession = Depends(get_db),
):
    """SRE edits the recommended action text before approving."""
    result = await db.execute(select(PreIncidentAlert).where(PreIncidentAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status != "open":
        raise HTTPException(status_code=409, detail=f"Alert is already '{alert.status}'")

    alert.edited_action = body.edited_action
    await db.commit()
    await db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/dismiss", response_model=AlertOut)
async def dismiss_alert(
    alert_id: uuid.UUID,
    body: DismissAlertRequest,
    user: TokenPayload = Depends(SREOrAdmin),
    db: AsyncSession = Depends(get_db),
):
    """SRE dismisses an alert from the queue without approving the action."""
    result = await db.execute(select(PreIncidentAlert).where(PreIncidentAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status not in ("open",):
        raise HTTPException(status_code=409, detail=f"Cannot dismiss an alert with status '{alert.status}'")

    alert.status = "dismissed"
    alert.handled_by = body.dismissed_by
    alert.handled_at = datetime.now(timezone.utc)

    action = AgentAction(
        id=uuid.uuid4(),
        tool_name="proactive_forecasting",
        service_id=alert.service_id,
        trigger="user_request",
        autonomy_tier="propose",
        approver=body.dismissed_by,
        description=f"Alert {alert_id} dismissed by {body.dismissed_by}. Reason: {body.reason or 'none'}",
        executed_at=datetime.now(timezone.utc),
    )
    db.add(action)
    await db.commit()
    await db.refresh(alert)
    return alert


# ── Pre-mortem reports ────────────────────────────────────────────────────────

@router.get("/reports", response_model=list[ReportOut], dependencies=[Depends(AnyAuthenticated)])
async def list_reports(
    status: str | None = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PreMortemReport).order_by(desc(PreMortemReport.created_at))
    if status:
        stmt = stmt.where(PreMortemReport.status == status)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/reports/{report_id}", response_model=ReportOut, dependencies=[Depends(AnyAuthenticated)])
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PreMortemReport).where(PreMortemReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/reports/{report_id}/approve", response_model=ReportOut)
async def approve_report(
    report_id: uuid.UUID,
    body: ApproveReportRequest,
    user: TokenPayload = Depends(SREOrAdmin),
    db: AsyncSession = Depends(get_db),
):
    """Human sign-off on a draft pre-mortem report."""
    result = await db.execute(select(PreMortemReport).where(PreMortemReport.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status not in ("draft", "pending_review"):
        raise HTTPException(status_code=409, detail=f"Report is already '{report.status}' — cannot approve")

    report.status = "approved"
    report.reviewed_by = body.reviewed_by
    report.reviewed_at = datetime.now(timezone.utc)
    report.reviewer_notes = body.notes
    await db.commit()
    await db.refresh(report)
    return report


@router.get("/reports/{report_id}/export")
async def export_report(
    report_id: uuid.UUID,
    fmt: Literal["markdown", "pdf"] = "markdown",
    user: TokenPayload = Depends(AnyAuthenticated),
    db: AsyncSession = Depends(get_db),
):
    """Download a pre-mortem report as Markdown or PDF."""
    result = await db.execute(select(PreMortemReport).where(PreMortemReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if fmt == "pdf":
        try:
            import markdown as md
            from weasyprint import HTML
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="PDF export requires the optional 'markdown' and 'weasyprint' packages.",
            )
        html_body = md.markdown(report.body_markdown, extensions=["tables"])
        pdf_bytes = HTML(string=f"<html><body>{html_body}</body></html>").write_pdf()
        return Response(content=pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=premortem-{report_id}.pdf"})

    return Response(content=report.body_markdown, media_type="text/markdown",
                    headers={"Content-Disposition": f"attachment; filename=premortem-{report_id}.md"})


# ── Autonomy policy management ────────────────────────────────────────────────

@router.get("/policy", response_model=list[PolicyOut], dependencies=[Depends(AnyAuthenticated)])
async def list_policies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AutonomyPolicy).order_by(AutonomyPolicy.tool_name))
    return result.scalars().all()


@router.put("/policy/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: uuid.UUID,
    body: UpdatePolicyRequest,
    user: TokenPayload = Depends(AdminOnly),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: update the autonomy tier for a specific tool+environment."""
    result = await db.execute(select(AutonomyPolicy).where(AutonomyPolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.autonomy_tier = body.autonomy_tier
    await db.commit()
    await db.refresh(policy)
    return policy
