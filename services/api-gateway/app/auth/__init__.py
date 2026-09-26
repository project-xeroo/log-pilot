"""
JWT authentication utilities.
Handles token creation, validation, and the get_current_user FastAPI dependency.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Token models
# ---------------------------------------------------------------------------

class TokenPayload(BaseModel):
    sub: str           # user UUID
    role: str
    org: str | None = None
    exp: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Token creation / verification
# ---------------------------------------------------------------------------

def create_access_token(user_id: uuid.UUID, role: str, org_id: uuid.UUID | None = None) -> str:
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(seconds=settings.jwt_expiry_seconds)
    payload = {
        "sub": str(user_id),
        "role": role,
        "org": str(org_id) if org_id else None,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**raw)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> TokenPayload:
    """FastAPI dependency: parse and validate the Bearer JWT."""
    return decode_access_token(credentials.credentials)


# Role hierarchy for RBAC — higher index = more privilege
_ROLE_RANK = {
    "viewer": 0,
    "junior": 1,
    "developer": 2,
    "manager": 2,
    "sre": 3,
    "admin": 4,
}


def require_role(minimum_role: str):
    """
    FastAPI dependency factory: raise 403 if the caller's role is below minimum_role.

    Usage:
        @router.get("/admin-only")
        async def admin_only(user = Depends(require_role("admin"))):
            ...
    """
    async def _check(
        user: Annotated[TokenPayload, Depends(get_current_user)],
    ) -> TokenPayload:
        caller_rank = _ROLE_RANK.get(user.role, -1)
        required_rank = _ROLE_RANK.get(minimum_role, 999)
        if caller_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires '{minimum_role}' role or above.",
            )
        return user

    return _check
