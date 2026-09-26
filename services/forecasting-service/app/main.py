"""Forecasting service — FastAPI health endpoint + Celery entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="LogPilot Forecasting Service", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "forecasting-service"}
