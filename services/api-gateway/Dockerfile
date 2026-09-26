FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ ./app/

# Install shared package from mounted volume in docker-compose
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
