from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/weights")
async def proxy_weights() -> Any:
    """Proxy to forecasting service — no auth required (read-only observability)."""
    try:
        resp = httpx.get(f"{settings.forecasting_service_url}/feedback/weights", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Forecasting service error: {exc}") from exc


@router.get("/weights/{indicator_name}")
async def proxy_weight(indicator_name: str) -> Any:
    try:
        resp = httpx.get(
            f"{settings.forecasting_service_url}/feedback/weights/{indicator_name}", timeout=10.0
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Forecasting service error: {exc}") from exc
