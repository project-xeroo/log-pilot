FROM python:3.11-slim

WORKDIR /app

<<<<<<< HEAD
COPY pyproject.toml .
COPY app/ ./app/

# Install shared package from mounted volume in docker-compose
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
=======
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
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
