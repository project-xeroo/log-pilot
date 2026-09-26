FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared/

COPY services/api-gateway/pyproject.toml /app/service/
COPY services/api-gateway/ /app/service/
RUN pip install --no-cache-dir /app/service/

WORKDIR /app/service

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
