FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

# Worker imports the ingestion service's parsers and PII redaction
COPY services/log-ingestion-service/app/ /app/log_ingestion_service/app/

COPY services/processing-worker/ /app/service/
RUN pip install /app/service/

WORKDIR /app/service

CMD ["celery", "-A", "app.main.celery_app", "worker", "--loglevel=info", "-Q", "ingestion,embeddings,anomaly", "--concurrency=4"]
