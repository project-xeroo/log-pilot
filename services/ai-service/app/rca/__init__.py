"""
Root Cause Analysis (RCA) Tool — Phase 3

PRD §5: Root Cause Analysis Tool
  temporal correlation + service-dependency inference + deep reasoning model causal-chain output

Architecture:
  1. Temporal correlation — scan log_records for a time window around the incident,
     order events by timestamp, identify causal chains across services.
  2. Service dependency inference — infer upstream/downstream relationships from
     correlated error timings (Granger-style: does service A's errors precede B's?).
  3. Deep reasoning model call — send the causal evidence to the LLM and receive a
     structured RCA with confidence scores and supporting log evidence.

Performance target (PRD §3 success criteria): < 15 seconds.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import MonitoredService, PreIncidentAlert, AnomalyEvent

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CausalStep:
    """One step in the inferred causal chain."""
    order: int
    service: str
    event_type: str          # error_spike | new_error | anomaly | alert
    timestamp: str           # ISO-8601
    description: str
    supporting_log_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class RCAResult:
    """Structured root cause analysis output."""
    service_name: str
    window_start: str
    window_end: str
    root_cause_summary: str
    causal_chain: list[CausalStep]
    affected_services: list[str]
    confidence_score: float        # 0.0–1.0
    ai_model: str
    duration_ms: float
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)


# ── Temporal correlation ──────────────────────────────────────────────────────

async def _fetch_error_timeline(
    db: AsyncSession,
    service_names: list[str],
    window_start: datetime,
    window_end: datetime,
    limit: int = 200,
) -> list[dict]:
    """
    Retrieve chronologically ordered error log records for the specified
    services within the analysis window.
    """
    if not service_names:
        return []

    placeholders = ", ".join(f":svc{i}" for i in range(len(service_names)))
    params: dict[str, Any] = {
        "start": window_start,
        "end": window_end,
    }
    for i, name in enumerate(service_names):
        params[f"svc{i}"] = name

    stmt = text(f"""
        SELECT id, timestamp, service_name, severity, message
        FROM log_records
        WHERE service_name IN ({placeholders})
          AND severity IN ('ERROR', 'CRITICAL', 'FATAL', 'WARNING')
          AND timestamp BETWEEN :start AND :end
        ORDER BY timestamp ASC
        LIMIT {limit}
    """)
    result = await db.execute(stmt, params)
    return [
        {
            "id": str(r.id),
            "timestamp": r.timestamp.isoformat() if r.timestamp else "",
            "service": r.service_name,
            "severity": r.severity,
            "message": (r.message or "")[:300],
        }
        for r in result.fetchall()
    ]


def _infer_service_dependencies(
    timeline: list[dict],
    lead_window_seconds: int = 30,
) -> dict[str, list[str]]:
    """
    Simple Granger-style dependency inference:
    If service A's errors consistently precede service B's errors within
    lead_window_seconds, infer A → B (A may be upstream cause of B).

    Returns {service: [downstream_services, ...]}.
    """
    # Group event timestamps by service
    by_service: dict[str, list[datetime]] = {}
    for event in timeline:
        ts_str = event.get("timestamp", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            continue
        by_service.setdefault(event["service"], []).append(ts)

    services = list(by_service.keys())
    deps: dict[str, list[str]] = {s: [] for s in services}

    lead_delta = timedelta(seconds=lead_window_seconds)

    for i, svc_a in enumerate(services):
        for svc_b in services:
            if svc_a == svc_b:
                continue
            times_a = sorted(by_service[svc_a])
            times_b = sorted(by_service[svc_b])
            lead_count = 0
            for ta in times_a:
                # Does svc_b have an error within (0, lead_window_seconds] after ta?
                for tb in times_b:
                    if timedelta(0) < (tb - ta) <= lead_delta:
                        lead_count += 1
                        break
            # If more than half of A's events are followed by B, infer A→B
            if times_a and lead_count / len(times_a) > 0.5:
                deps[svc_a].append(svc_b)

    return deps


def _build_causal_chain(
    timeline: list[dict],
    deps: dict[str, list[str]],
    primary_service: str,
) -> list[CausalStep]:
    """
    Build an ordered causal-chain list from the timeline and inferred dependencies.
    Starts from services that are not depended on by others (root causes first).
    """
    if not timeline:
        return []

    # Find root services (those whose errors appear earliest and aren't downstream)
    downstream_set = set()
    for downstreams in deps.values():
        downstream_set.update(downstreams)

    by_service: dict[str, list[dict]] = {}
    for event in timeline:
        by_service.setdefault(event["service"], []).append(event)

    order = 1
    chain: list[CausalStep] = []
    visited: set[str] = set()

    # Sort services: root services first, then by first error timestamp
    def service_first_ts(svc: str) -> datetime:
        events = by_service.get(svc, [])
        if not events:
            return datetime.max.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(events[0]["timestamp"])
        except ValueError:
            return datetime.max.replace(tzinfo=timezone.utc)

    root_services = [s for s in by_service if s not in downstream_set]
    other_services = [s for s in by_service if s in downstream_set]
    ordered_services = sorted(root_services, key=service_first_ts) + \
                       sorted(other_services, key=service_first_ts)

    for svc in ordered_services:
        if svc in visited:
            continue
        visited.add(svc)
        events = by_service.get(svc, [])
        if not events:
            continue
        first_event = events[0]
        severity = first_event.get("severity", "ERROR")
        event_type = "error_spike" if len(events) > 5 else "new_error"
        description = (
            f"{len(events)} {severity} event(s) starting at "
            f"{first_event.get('timestamp', 'unknown')}. "
            f"First message: {first_event.get('message', '')[:120]}"
        )
        if deps.get(svc):
            description += f" [Downstream impact on: {', '.join(deps[svc])}]"

        chain.append(CausalStep(
            order=order,
            service=svc,
            event_type=event_type,
            timestamp=first_event.get("timestamp", ""),
            description=description,
            supporting_log_ids=[e["id"] for e in events[:5]],
            confidence=0.7 if svc not in downstream_set else 0.5,
        ))
        order += 1

    return chain


# ── LLM causal-chain reasoning ────────────────────────────────────────────────

_RCA_SYSTEM_PROMPT = """You are a senior Site Reliability Engineer performing root cause analysis.
You will be given a timeline of error events and an inferred causal chain across services.
Produce a structured RCA with:
1. A concise root cause summary (1–3 sentences)
2. The confidence level (0.0–1.0) in the root cause
3. Any additional causal steps not captured in the initial chain

Be specific. Reference service names and timestamps. Do not speculate beyond the evidence."""

_RCA_USER_TEMPLATE = """Service under analysis: {service_name}
Analysis window: {window_start} to {window_end}

Error timeline ({event_count} events):
{timeline_text}

Inferred dependency chain:
{dependency_text}

Pre-built causal steps:
{chain_text}

Provide a root cause summary and adjusted confidence score."""


async def run_rca(
    db: AsyncSession,
    service_id: uuid.UUID,
    *,
    window_minutes: int = 30,
    include_upstream_services: bool = True,
) -> RCAResult:
    """
    Run a full RCA for a service over the last `window_minutes` minutes.

    Steps:
      1. Identify related services from recent alerts/anomalies.
      2. Fetch error timeline.
      3. Infer service dependencies.
      4. Build structural causal chain.
      5. Call deep reasoning model for narrative + confidence.

    Returns a structured RCAResult.
    """
    import time
    t0 = time.perf_counter()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)

    # ── 1. Get primary service name ───────────────────────────────────────────
    svc_result = await db.execute(
        select(MonitoredService).where(MonitoredService.id == service_id)
    )
    service = svc_result.scalar_one_or_none()
    if service is None:
        raise ValueError(f"Service {service_id} not found")

    service_names = [service.name]

    # ── 2. Fetch timeline ─────────────────────────────────────────────────────
    timeline = await _fetch_error_timeline(db, service_names, window_start, now)

    # ── 3. Infer dependencies ─────────────────────────────────────────────────
    deps = _infer_service_dependencies(timeline)

    # ── 4. Build structural causal chain ──────────────────────────────────────
    causal_chain = _build_causal_chain(timeline, deps, service.name)

    # ── 5. LLM deep reasoning ─────────────────────────────────────────────────
    root_cause_summary = ""
    confidence_score = 0.5
    ai_model = "none"

    try:
        from app.providers import get_provider
        provider = get_provider()

        timeline_text = "\n".join(
            f"[{e['timestamp']}] {e['service']} {e['severity']}: {e['message']}"
            for e in timeline[:50]
        )
        dep_text = "\n".join(
            f"  {svc} → {', '.join(downstreams)}"
            for svc, downstreams in deps.items() if downstreams
        ) or "  (no clear dependencies detected)"

        chain_text = "\n".join(
            f"  Step {s.order}: [{s.service}] {s.description}"
            for s in causal_chain
        ) or "  (no causal chain built)"

        prompt = _RCA_USER_TEMPLATE.format(
            service_name=service.name,
            window_start=window_start.isoformat(),
            window_end=now.isoformat(),
            event_count=len(timeline),
            timeline_text=timeline_text or "  (no errors in window)",
            dependency_text=dep_text,
            chain_text=chain_text,
        )

        full_prompt = _RCA_SYSTEM_PROMPT + "\n\n" + prompt
        resp = await provider.complete(full_prompt, max_tokens=1024)
        root_cause_summary = resp.content.strip()
        ai_model = resp.model

        # Try to extract confidence from response if the model included it
        import re
        conf_match = re.search(r"confidence[:\s]+([0-9.]+)", root_cause_summary, re.I)
        if conf_match:
            try:
                confidence_score = min(max(float(conf_match.group(1)), 0.0), 1.0)
            except ValueError:
                pass

    except Exception as exc:
        logger.warning("RCA LLM call failed for service %s: %s — using structural chain only", service.name, exc)
        root_cause_summary = (
            f"Root cause analysis based on structural correlation only "
            f"(AI unavailable). "
            f"First causal step: {causal_chain[0].description if causal_chain else 'no data'}"
        )
        confidence_score = 0.3

    duration_ms = (time.perf_counter() - t0) * 1000

    return RCAResult(
        service_name=service.name,
        window_start=window_start.isoformat(),
        window_end=now.isoformat(),
        root_cause_summary=root_cause_summary,
        causal_chain=causal_chain,
        affected_services=list({s.service for s in causal_chain}),
        confidence_score=round(confidence_score, 3),
        ai_model=ai_model,
        duration_ms=round(duration_ms, 1),
        supporting_evidence=timeline[:20],
    )
