from fastapi import FastAPI
from app.handlers.audit_router import router

app = FastAPI(title="LogPilot Audit Service", version="1.0.0")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "audit-service"}
