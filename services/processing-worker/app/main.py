"""
Processing Worker — Celery application factory.
Configures queues, serialization, and task routing.
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery("logpilot-worker")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Queue routing
    task_routes={
        "app.tasks.ingestion.*": {"queue": "ingestion"},
        "app.tasks.embeddings.*": {"queue": "embeddings"},
        "app.tasks.anomaly.*": {"queue": "anomaly"},
        "analysis.*": {"queue": "anomaly"},
    },
    task_queues_config={
        "ingestion": {"exchange": "ingestion", "routing_key": "ingestion"},
        "embeddings": {"exchange": "embeddings", "routing_key": "embeddings"},
        "anomaly": {"exchange": "anomaly", "routing_key": "anomaly"},
    },
    # Retry defaults
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Concurrency
    worker_concurrency=4,
)

# Register every task module explicitly (autodiscover only looks for a
# `tasks` submodule, which would miss the analysis and embedding tasks)
celery_app.conf.include = [
    "app.tasks",             # Phase 1: parse → redact → store
    "app.embeddings",        # Phase 2: embedding generation
    "app.tasks.analysis",    # Phase 3: dedup → clustering → health → anomalies
]
