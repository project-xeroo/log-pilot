"""
Auth router — login and token refresh endpoints.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    CurrentUser,
    TokenResponse,
    create_access_token,
    hash_password,
    verify_password,
)
from shared.config import get_db
from shared.models import Role

# Roles a user may pick when self-registering; others are assigned by an admin
_SELF_SERVE_ROLES = {Role.developer, Role.junior, Role.viewer}

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    role: Role = Role.developer


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email + password.
    Returns a JWT access token.
    """
    result = await db.execute(
        text("SELECT id, hashed_password, role, is_active FROM users WHERE email = :email"),
        {"email": payload.email},
    )
    row = result.fetchone()

    if not row or not verify_password(payload.password, row.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    if not row.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )

    token = create_access_token(row.id, row.role)
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account (self-serve: developer, junior, or viewer).
    Admin, SRE, and manager accounts are assigned by an existing admin.
    """
    if payload.role not in _SELF_SERVE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"'{payload.role.value}' accounts must be assigned by an existing admin.",
        )

    existing = await db.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": payload.email}
    )
    if existing.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user_id = uuid.uuid4()
    hashed = hash_password(payload.password)
    await db.execute(
        text("""
            INSERT INTO users (id, email, hashed_password, full_name, role)
            VALUES (:id, :email, :hashed_password, :full_name, :role)
        """),
        {
            "id": str(user_id),
            "email": payload.email,
            "hashed_password": hashed,
            "full_name": payload.full_name,
            "role": payload.role.value,
        },
    )
    await db.commit()

    token = create_access_token(user_id, payload.role)
    return TokenResponse(access_token=token)


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    permissions: list[str]


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Return the caller's profile and effective permissions (drives UI gating)."""
    from shared.models import ROLE_PERMISSIONS

    result = await db.execute(
        text("SELECT id, email, full_name, role, is_active FROM users WHERE id = :id"),
        {"id": current_user.id},
    )
    row = result.fetchone()
    if not row or not row.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    role = Role(row.role)
    return MeResponse(
        id=str(row.id),
        email=row.email,
        full_name=row.full_name,
        role=role.value,
        permissions=sorted(p.value for p in ROLE_PERMISSIONS[role]),
    )
