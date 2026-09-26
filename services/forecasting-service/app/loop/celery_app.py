"""
Celery application factory and beat schedule for the forecasting service.
"""

from __future__ import annotations

import asyncio
from celery import Celery
from celery.utils.log import get_task_logger
from sqlalchemy import select

from shared.config import get_settings
from shared.models import MonitoredService
from shared.config import AsyncSessionLocal

settings = get_settings()
logger = get_task_logger(__name__)

celery_app = Celery(
    "forecasting",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.loop.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="forecasting.dispatch_all_services")
def dispatch_all_services() -> None:
    """
    Scheduled beat task: fetches all active services from the DB and
    dispatches one *run_cycle_for_service* task per service.
    Called on the global beat interval (default 60 s).
    """
    from app.loop.tasks import run_cycle_for_service

    async def _fetch_services():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MonitoredService).where(MonitoredService.is_active == True)
            )
            return result.scalars().all()

    services = asyncio.get_event_loop().run_until_complete(_fetch_services())
    for svc in services:
        run_cycle_for_service.apply_async(args=[str(svc.id)])
    logger.info("Dispatched forecasting tasks for %d services", len(services))


# Beat schedule — fires every N seconds for the dispatcher
celery_app.conf.beat_schedule = {
    "dispatch-all-services": {
        "task": "forecasting.dispatch_all_services",
        "schedule": settings.forecasting_loop_interval_seconds,
    },
}
