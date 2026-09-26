"""
HTTP entry points for the model-backed analysis tools, called by the gateway's
/analysis routes:

  POST /analysis/rca/{service_id}  — Root Cause Analysis tool (PRD §5.10)
  POST /analysis/compare           — Deployment Comparison tool (PRD §5.12)
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deployment import compare_deployments
from app.rca import run_rca

router = APIRouter(prefix="/analysis", tags=["analysis"])


async def _get_db() -> AsyncSession:  # type: ignore[return]
    """Overridden in main.py with the app's session factory."""
    raise NotImplementedError


class RCARequest(BaseModel):
    window_minutes: int = 30


class CompareRequest(BaseModel):
    service_id: uuid.UUID
    baseline_version: str
    head_version: str
    baseline_deployed_at: datetime | None = None
    head_deployed_at: datetime | None = None
    window_hours: int = 2


@router.post("/rca/{service_id}")
async def rca(
    service_id: uuid.UUID,
    body: RCARequest,
    db: AsyncSession = Depends(_get_db),
) -> dict[str, Any]:
    try:
        result = await run_rca(db, service_id, window_minutes=body.window_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asdict(result)


@router.post("/compare")
async def compare(
    body: CompareRequest,
    db: AsyncSession = Depends(_get_db),
) -> dict[str, list[str]]:
    """Run the comparison; returns the ids of the regressions it recorded."""
    try:
        regressions = await compare_deployments(
            db,
            service_id=body.service_id,
            baseline_version=body.baseline_version,
            head_version=body.head_version,
            baseline_deployed_at=body.baseline_deployed_at,
            head_deployed_at=body.head_deployed_at,
            window_hours=body.window_hours,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"regression_ids": [str(r.id) for r in regressions]}
