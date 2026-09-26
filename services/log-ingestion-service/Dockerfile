FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared package first
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

# Install service dependencies
COPY services/log-ingestion-service/pyproject.toml /app/service/
COPY services/log-ingestion-service/ /app/service/
RUN pip install --no-cache-dir /app/service/

WORKDIR /app/service

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
