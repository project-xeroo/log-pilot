<<<<<<< HEAD
from __future__ import annotations

from fastapi import Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint
import time
import logging

logger = logging.getLogger("api-gateway")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
=======
"""
Audit logging middleware.
Every request by an authenticated user is recorded in agent_actions.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger()


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Records every API request + response in the agent_actions table.
    Skips /health and /docs/* endpoints.
    """

    _SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self._SKIP_PATHS or request.url.path.startswith("/docs"):
            return await call_next(request)

        start = time.perf_counter()
        user_id: uuid.UUID | None = None

        # Attempt to extract user from Authorization header without raising
        try:
            from app.auth import decode_access_token
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                payload = decode_access_token(auth[7:])
                user_id = uuid.UUID(payload.sub)
        except Exception:
            pass

        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        log.info(
            "api.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            user_id=str(user_id) if user_id else None,
            elapsed_ms=round(elapsed_ms, 2),
        )

        # Fire-and-forget DB write (non-blocking)
        try:
            db_factory = request.app.state.db_factory
            if db_factory:
                import asyncio
                asyncio.create_task(
                    _write_audit_record(
                        db_factory=db_factory,
                        method=request.method,
                        path=request.url.path,
                        status=response.status_code,
                        user_id=user_id,
                        elapsed_ms=elapsed_ms,
                    )
                )
        except Exception:
            pass  # Audit failure must never break the request

        return response


async def _write_audit_record(
    db_factory,
    method: str,
    path: str,
    status: int,
    user_id: uuid.UUID | None,
    elapsed_ms: float,
) -> None:
    try:
        async with db_factory() as db:
            from sqlalchemy import text
            await db.execute(
                text("""
                    INSERT INTO agent_actions (
                        tool_name, trigger, autonomy_tier,
                        actor_user_id, input_summary, output_summary, status
                    ) VALUES (
                        :tool_name, 'user', 'read_only'::autonomytier,
                        :user_id::uuid,
                        :input_summary, :output_summary, :status
                    )
                """),
                {
                    "tool_name": f"api.{method.lower()}",
                    "user_id": str(user_id) if user_id else None,
                    "input_summary": path,
                    "output_summary": f"status={status}",
                    "status": "completed" if status < 400 else "failed",
                },
            )
            await db.commit()
    except Exception as exc:
        log.warning("audit.write_failed", error=str(exc))
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
