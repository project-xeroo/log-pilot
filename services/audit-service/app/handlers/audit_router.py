"""
Audit service — thin FastAPI service exposing the agent_actions audit log.

Provides:
  GET  /audit/actions          — paginated list of all agent actions
  GET  /audit/actions/{id}     — single action detail
  POST /audit/actions/{id}/reverse  — mark an action as reversed (SRE-initiated)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_db
from shared.models import AgentAction

router = APIRouter(prefix="/audit", tags=["audit"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AgentActionOut(BaseModel):
    id: uuid.UUID
    tool_name: str
    service_id: uuid.UUID | None
    trigger: str
    confidence: float | None
    autonomy_tier: str
    approver: str | None
    description: str | None
    reversed: bool
    reversed_by: str | None
    reversed_at: datetime | None
    executed_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ReverseActionRequest(BaseModel):
    reversed_by: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/actions", response_model=list[AgentActionOut])
async def list_actions(
    tool_name: str | None = None,
    service_id: uuid.UUID | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated, reverse-chronological list of agent actions."""
    stmt = select(AgentAction).order_by(desc(AgentAction.executed_at))
    if tool_name:
        stmt = stmt.where(AgentAction.tool_name == tool_name)
    if service_id:
        stmt = stmt.where(AgentAction.service_id == service_id)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/actions/{action_id}", response_model=AgentActionOut)
async def get_action(action_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentAction).where(AgentAction.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


@router.post("/actions/{action_id}/reverse", response_model=AgentActionOut)
async def reverse_action(
    action_id: uuid.UUID,
    body: ReverseActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark an agent action as reversed. This is the reversibility guarantee
    required by the success criteria — 100% of high-impact actions must
    be reversible through this endpoint.
    """
    result = await db.execute(select(AgentAction).where(AgentAction.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.reversed:
        raise HTTPException(status_code=409, detail="Action has already been reversed")

    action.reversed = True
    action.reversed_by = body.reversed_by
    action.reversed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(action)
    return action
