"""
JWT authentication and RBAC for the API Gateway.

Authorization uses the permission model in ``shared.models`` (PRD §10):
every route declares the ``Permission`` it needs, and ``ROLE_PERMISSIONS``
maps each role to its permission set.

Tokens are stateless: the JWT carries the user id (``sub``), role, and org.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel

from app.config import settings
from shared.models import Permission, Role, has_permission

_bearer = HTTPBearer()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

# bcrypt only uses the first 72 bytes of a password
def _secret(plain: str) -> bytes:
    return plain.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_secret(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_secret(plain), hashed.encode("ascii"))
    except ValueError:  # malformed hash
        return False


# ---------------------------------------------------------------------------
# Token models
# ---------------------------------------------------------------------------

class TokenPayload(BaseModel):
    sub: str           # user UUID
    role: str
    org: str | None = None
    exp: int

    @property
    def id(self) -> uuid.UUID:
        return uuid.UUID(self.sub)

    def can(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = settings.jwt_expiry_seconds


# ---------------------------------------------------------------------------
# Token creation / verification
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: uuid.UUID | str, role: Role | str, org_id: uuid.UUID | None = None
) -> str:
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(seconds=settings.jwt_expiry_seconds)
    payload = {
        "sub": str(user_id),
        "role": Role(role).value,
        "org": str(org_id) if org_id else None,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**raw)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> TokenPayload:
    """Parse and validate the Bearer JWT."""
    return decode_access_token(credentials.credentials)


CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


def permission_checker(permission: Permission):
    """Dependency callable enforcing ``permission``; returns the caller's token.

    Usage: ``user: Annotated[TokenPayload, Depends(permission_checker(Permission.x))]``
    """

    async def _check(current_user: CurrentUser) -> TokenPayload:
        if not current_user.can(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' lacks permission '{permission.value}'",
            )
        return current_user

    return _check


def require_permission(permission: Permission):
    """Route dependency enforcing ``permission``.

    Usage: ``@router.get(..., dependencies=[require_permission(Permission.x)])``
    """
    return Depends(permission_checker(permission))


def require_roles(*roles: Role | str):
    """Dependency callable allowing only the given roles (use with ``Depends``)."""
    allowed = {Role(r).value for r in roles}

    async def _check(current_user: CurrentUser) -> TokenPayload:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not allowed. Required: {sorted(allowed)}",
            )
        return current_user

    return _check


__all__ = [
    "hash_password",
    "verify_password",
    "TokenPayload",
    "TokenResponse",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "CurrentUser",
    "permission_checker",
    "require_permission",
    "require_roles",
]
