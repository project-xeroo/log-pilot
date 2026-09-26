from __future__ import annotations

import logging

from fastapi import FastAPI

from app.handlers import router as export_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="LogPilot Audit Service",
    version="0.5.0",
    description="Export incident reports as PDF or Markdown",
)

app.include_router(export_router)


@app.get("/healthz")
def health():
    return {"status": "ok", "service": "audit-service"}
