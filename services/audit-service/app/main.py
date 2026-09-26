<<<<<<< HEAD
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
=======
from fastapi import FastAPI
from app.handlers.audit_router import router

app = FastAPI(title="LogPilot Audit Service", version="1.0.0")
app.include_router(router)


@app.get("/health")
async def health():
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
    return {"status": "ok", "service": "audit-service"}
