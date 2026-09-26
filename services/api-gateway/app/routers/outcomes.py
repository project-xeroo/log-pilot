from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_permission
from shared.models import IncidentOutcome, OutcomeVerdict, Permission
from shared.utils import get_session

router = APIRouter(prefix="/outcomes", tags=["outcomes"])

DBSession = Annotated[Session, Depends(get_session)]


class OutcomeCreate(BaseModel):
    incident_id: str
    report_id: str | None = None
    verdict: OutcomeVerdict
    rca_accurate: bool | None = None
    forecast_accurate: bool | None = None
    time_to_detect_seconds: float | None = None
    time_to_resolve_seconds: float | None = None
    action_taken: str | None = None
    fired_indicators: list[str] | None = None
    forecast_score_at_incident: float | None = None
    notes: str | None = None


class OutcomeOut(BaseModel):
    id: str
    incident_id: str
    report_id: str | None
    verdict: str
    rca_accurate: bool | None
    forecast_accurate: bool | None
    time_to_detect_seconds: float | None
    time_to_resolve_seconds: float | None
    action_taken: str | None
    fired_indicators: list[str] | None
    forecast_score_at_incident: float | None
    notes: str | None
    reviewed_by_id: str | None

    model_config = {"from_attributes": True}


@router.post(
    "",
    response_model=OutcomeOut,
    status_code=201,
    dependencies=[require_permission(Permission.outcome_write)],
)
def create_outcome(
    body: OutcomeCreate,
    current_user: CurrentUser,
    session: DBSession,
):
    """Log an incident outcome and trigger forecasting weight feedback."""
    outcome = IncidentOutcome(
        incident_id=body.incident_id,
        report_id=uuid.UUID(body.report_id) if body.report_id else None,
        verdict=body.verdict,
        rca_accurate=body.rca_accurate,
        forecast_accurate=body.forecast_accurate,
        time_to_detect_seconds=body.time_to_detect_seconds,
        time_to_resolve_seconds=body.time_to_resolve_seconds,
        action_taken=body.action_taken,
        fired_indicators=body.fired_indicators,
        forecast_score_at_incident=body.forecast_score_at_incident,
        notes=body.notes,
        reviewed_by_id=current_user.id,
    )
    session.add(outcome)
    session.flush()

    # Fire-and-forget: notify forecasting service to update weights
    import httpx
    from app.config import settings

    try:
        httpx.post(
            f"{settings.forecasting_service_url}/feedback/ingest",
            json={
                "outcome_id": str(outcome.id),
                "verdict": body.verdict.value,
                "fired_indicators": body.fired_indicators or [],
                "forecast_accurate": body.forecast_accurate,
            },
            timeout=5.0,
        )
    except Exception:
        pass  # non-blocking — outcome is persisted regardless

    return OutcomeOut.model_validate(outcome)


@router.get(
    "",
    dependencies=[require_permission(Permission.outcome_read)],
)
def list_outcomes(
    session: DBSession,
    incident_id: str | None = None,
    verdict: OutcomeVerdict | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = session.query(IncidentOutcome)
    if incident_id:
        q = q.filter(IncidentOutcome.incident_id == incident_id)
    if verdict:
        q = q.filter(IncidentOutcome.verdict == verdict)
    q = q.order_by(IncidentOutcome.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [OutcomeOut.model_validate(o) for o in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{outcome_id}",
    response_model=OutcomeOut,
    dependencies=[require_permission(Permission.outcome_read)],
)
def get_outcome(outcome_id: str, session: DBSession):
    outcome = session.get(IncidentOutcome, uuid.UUID(outcome_id))
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not found")
    return OutcomeOut.model_validate(outcome)
