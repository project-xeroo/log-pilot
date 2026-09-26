from fastapi import FastAPI
from app.handlers import router as export_router
from app.handlers.audit_router import router as audit_router

app = FastAPI(title="LogPilot Audit Service", version="1.0.0")
app.include_router(audit_router)
app.include_router(export_router)   # /export/{markdown,pdf} — used by gateway report export


@app.get("/health")
async def health():
    return {"status": "ok", "service": "audit-service"}
