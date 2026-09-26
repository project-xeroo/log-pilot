"""
JWT authentication and RBAC for the API Gateway.

Roles (PRD §10):
  viewer      — Junior Engineer (read-only, guided mode)
  developer   — Software Engineer
  devops      — DevOps Engineer
  sre         — Site Reliability Engineer (can approve actions)
  admin       — Full access including autonomy policy configuration

Every route that mutates state requires the caller's role to be in the
allowed_roles set.  Role is embedded in the JWT payload as "role".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from shared.config import get_settings

settings = get_settings()
_bearer = HTTPBearer()


# ── Token schemas ─────────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub: str          # username / user ID
    role: str         # viewer | developer | devops | sre | admin
    exp: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Token creation ────────────────────────────────────────────────────────────

def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {"sub": subject, "role": role, "exp": int(expire.timestamp())}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> TokenPayload:
    token = credentials.credentials
    try:
        raw = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**raw)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_roles(*roles: str):
    """
    Returns a FastAPI dependency that raises 403 unless the current user
    has one of the specified roles.
    """
    allowed = set(roles)

    async def _check(user: Annotated[TokenPayload, Depends(get_current_user)]) -> TokenPayload:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not allowed. Required: {sorted(allowed)}",
            )
        return user

    return _check


# Convenience aliases
SREOrAdmin = require_roles("sre", "admin")
AnyAuthenticated = require_roles("viewer", "developer", "devops", "sre", "admin")
AdminOnly = require_roles("admin")
