FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY services/forecasting-service/ /app/service/
RUN pip install /app/service/

WORKDIR /app/service

# Same image runs the Celery worker and beat (see docker-compose.yml)
EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
