FROM python:3.11-slim

WORKDIR /app

# WeasyPrint system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 \
    libffi-dev shared-mime-info fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY app/ ./app/

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
