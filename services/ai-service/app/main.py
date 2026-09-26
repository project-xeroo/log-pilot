from __future__ import annotations

import logging

from fastapi import FastAPI

from app.reports import router as reports_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="LogPilot AI Service",
    version="0.5.0",
    description="LLM-powered incident report generation and RCA",
)

app.include_router(reports_router)


@app.get("/healthz")
def health():
    return {"status": "ok", "service": "ai-service"}
