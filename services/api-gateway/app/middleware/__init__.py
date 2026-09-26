"""
Request logging middleware for the API Gateway.

Every request is logged with method, path, status, and duration.
"""
from __future__ import annotations

import time
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger()


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every API request + response.
    Skips /health and /docs/* endpoints.
    """

    _SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        if request.url.path not in self._SKIP_PATHS:
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration_ms, 1),
            )
        return response


# Name used by the Phase 3/4 gateway
RequestLoggingMiddleware = AuditLoggingMiddleware
