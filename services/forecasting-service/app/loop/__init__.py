<<<<<<< HEAD
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.loop.feedback import apply_outcome_feedback
from shared.models import ForecastWeight, OutcomeVerdict
from shared.utils import get_session

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = logging.getLogger("forecasting.feedback_router")

DBSession = Annotated[Session, Depends(get_session)]


class FeedbackIngest(BaseModel):
    outcome_id: str
    verdict: OutcomeVerdict
    fired_indicators: list[str] = []
    forecast_accurate: bool | None = None


class WeightOut(BaseModel):
    indicator_name: str
    weight: float
    precision: float
    recall: float
    total_fired: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int

    model_config = {"from_attributes": True}


@router.post("/ingest")
def ingest(body: FeedbackIngest, session: DBSession):
    """Receive an outcome verdict and update indicator weights."""
    updates = apply_outcome_feedback(
        session=session,
        verdict=body.verdict,
        fired_indicators=body.fired_indicators,
        forecast_accurate=body.forecast_accurate,
    )
    return {"outcome_id": body.outcome_id, "weight_updates": updates}


@router.get("/weights")
def list_weights(session: DBSession):
    """Return all current indicator weights for observability."""
    weights = session.query(ForecastWeight).order_by(ForecastWeight.weight.desc()).all()
    return {"items": [WeightOut.model_validate(w) for w in weights]}


@router.get("/weights/{indicator_name}")
def get_weight(indicator_name: str, session: DBSession):
    fw = session.query(ForecastWeight).filter_by(indicator_name=indicator_name).first()
    if not fw:
        raise HTTPException(status_code=404, detail="Indicator not found")
    return WeightOut.model_validate(fw)
=======
from .celery_app import celery_app
from .tasks import run_cycle_for_service
from .autonomy import resolve_autonomy_tier, record_action

__all__ = ["celery_app", "run_cycle_for_service", "resolve_autonomy_tier", "record_action"]
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
