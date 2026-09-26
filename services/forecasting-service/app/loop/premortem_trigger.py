"""
Pre-mortem report trigger.

When a service crosses the critical threshold, the forecasting loop
calls this module to draft a pre-mortem report automatically (PRD §4.3).
The draft is written with status='draft' and requires human sign-off.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import PreMortemReport, PreIncidentAlert, MonitoredService
from app.loop.autonomy import resolve_autonomy_tier, record_action

logger = logging.getLogger(__name__)


async def maybe_draft_premortem(
    db: AsyncSession,
    *,
    service: MonitoredService,
    alert: PreIncidentAlert,
    ai_assisted: bool,
) -> PreMortemReport | None:
    """
    Draft a pre-mortem report if the autonomy policy allows it for
    "pre_mortem_report" tool. Always requires human sign-off (status=draft).
    """
    tier = await resolve_autonomy_tier(
        db,
        tool_name="pre_mortem_report",
        environment=service.environment,
        service_id=service.id,
    )

    # "observe" tier means no autonomous drafting
    if tier == "observe":
        logger.info("Pre-mortem draft suppressed by autonomy policy (observe) for %s", service.name)
        return None

    now = datetime.now(timezone.utc)
    body = _build_premortem_body(service, alert, ai_assisted, now)

    report = PreMortemReport(
        id=uuid.uuid4(),
        service_id=service.id,
        alert_id=alert.id,
        title=f"Pre-Mortem Draft: {service.name} — {now.strftime('%Y-%m-%d %H:%M UTC')}",
        body_markdown=body,
        status="draft",
    )
    db.add(report)
    await db.flush()

    await record_action(
        db,
        tool_name="pre_mortem_report",
        service_id=service.id,
        trigger="alert_threshold",
        confidence=alert.confidence,
        autonomy_tier=tier,
        description=f"Pre-mortem report drafted for {service.name} (alert {alert.id})",
    )

    return report


def _build_premortem_body(
    service: MonitoredService,
    alert: PreIncidentAlert,
    ai_assisted: bool,
    now: datetime,
) -> str:
    actions_md = ""
    if alert.recommended_actions:
        actions_md = "\n".join(
            f"{i + 1}. {a['action']}" for i, a in enumerate(alert.recommended_actions)
        )

    similar_md = ""
    if alert.similar_past_event_ids:
        similar_md = ", ".join(alert.similar_past_event_ids[:3])

    return f"""# Pre-Mortem Report: {service.name}

> **Status:** Draft — awaiting human review and sign-off
> **Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}
> **AI Assisted:** {"Yes" if ai_assisted else "No (threshold-based fallback)"}

---

## Summary

Service **{service.name}** (env: `{service.environment}`) has crossed the **critical** risk
threshold with a composite risk score of **{alert.risk_score:.1f}/100**.

## Risk Signals

| Signal | Detail |
|---|---|
| Risk tier | `{alert.risk_tier}` |
| Composite score | `{alert.risk_score:.1f}` |
| Matched pattern | `{alert.matched_pattern or "—"}` |
| Confidence | `{f"{alert.confidence:.2%}" if alert.confidence else "—"}` |
| Similar past events | {similar_md or "—"} |

## Agent Explanation

{alert.explanation}

## Recommended Actions

{actions_md or "_No recommendations generated._"}

---

## Investigation Checklist

- [ ] Review error logs for the last 15 minutes
- [ ] Check recent deployments (last 2 hours)
- [ ] Confirm downstream service health
- [ ] Verify database connection pool usage
- [ ] Assess user impact

## Timeline

| Time | Event |
|---|---|
| {alert.alerted_at.strftime('%H:%M:%S UTC')} | Risk threshold crossed — alert created |
| _(pending)_ | SRE notified |
| _(pending)_ | Investigation started |
| _(pending)_ | Resolution |

---
_This report was drafted autonomously by the LogPilot Agent.
It requires human review and sign-off before it is considered final._
"""
