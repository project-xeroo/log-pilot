FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

# Worker needs access to the ingestion service parsers/redaction
COPY services/log-ingestion-service/ /app/log_ingestion_service/

COPY services/processing-worker/pyproject.toml /app/service/
COPY services/processing-worker/ /app/service/
RUN pip install --no-cache-dir /app/service/
# Install psycopg2 explicitly (needed for sync Celery tasks)
RUN pip install --no-cache-dir psycopg2-binary

WORKDIR /app/service

ENV PYTHONPATH=/app

CMD ["celery", "-A", "app.main.celery_app", "worker", "--loglevel=info", "-Q", "ingestion,embeddings,anomaly", "--concurrency=4"]
