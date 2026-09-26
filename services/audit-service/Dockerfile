FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# WeasyPrint runtime libraries (PDF export)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        shared-mime-info fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY services/audit-service/ /app/service/
RUN pip install /app/service/

WORKDIR /app/service

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
