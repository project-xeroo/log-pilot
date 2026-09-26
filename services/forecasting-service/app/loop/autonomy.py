"""
Autonomy policy resolver and action recorder.

Checks the autonomy_policy table for the effective tier of a given tool
in the given environment, with automatic downgrade to "propose" if no
policy row is found (PRD §8.2, §8.3).
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import AutonomyPolicy, AgentAction
from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def resolve_autonomy_tier(
    db: AsyncSession,
    tool_name: str,
    environment: str,
    service_id: uuid.UUID | None = None,
) -> str:
    """
    Resolve the effective autonomy tier for (tool, environment, service).
    Priority: service-specific row > global row (service_id IS NULL) > default.
    Any tier not in {observe, propose, auto} is downgraded to 'propose'.
    """
    # Try service-specific first
    for sid in ([service_id, None] if service_id else [None]):
        stmt = select(AutonomyPolicy).where(
            AutonomyPolicy.tool_name == tool_name,
            AutonomyPolicy.environment == environment,
            AutonomyPolicy.service_id == sid,
        )
        result = await db.execute(stmt)
        policy = result.scalar_one_or_none()
        if policy:
            tier = policy.autonomy_tier
            if tier not in ("observe", "propose", "auto"):
                logger.warning(
                    "Unknown autonomy tier '%s' for tool '%s' — downgrading to 'propose'",
                    tier, tool_name,
                )
                return "propose"
            return tier

    return settings.default_autonomy_tier


async def record_action(
    db: AsyncSession,
    *,
    tool_name: str,
    service_id: uuid.UUID | None,
    trigger: str,
    confidence: float | None,
    autonomy_tier: str,
    description: str,
    approver: str | None = None,
) -> AgentAction:
    """Write an immutable audit record for every agent action."""
    action = AgentAction(
        id=uuid.uuid4(),
        tool_name=tool_name,
        service_id=service_id,
        trigger=trigger,
        confidence=confidence,
        autonomy_tier=autonomy_tier,
        approver=approver,
        description=description,
        executed_at=datetime.now(timezone.utc),
    )
    db.add(action)
    await db.flush()
    return action
