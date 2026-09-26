"""
Auth router — login and token refresh endpoints.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, verify_password, hash_password, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    role: str = "developer"


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(),  # injected by the app via dependency override
):
    """
    Authenticate with email + password.
    Returns a JWT access token.
    """
    from app.config import settings

    result = await db.execute(
        text("SELECT id, hashed_password, role, organization_id, is_active FROM users WHERE email = :email"),
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

    token = create_access_token(
        user_id=row.id,
        role=row.role,
        org_id=row.organization_id,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expiry_seconds)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(),
):
    """
    Register a new user account (self-serve, developer/junior roles only).
    Admins and SREs are created by existing admins.
    """
    from app.config import settings

    if payload.role in ("admin", "sre"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin and SRE accounts must be created by an existing admin.",
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
            VALUES (:id, :email, :hashed_password, :full_name, :role::userrole)
        """),
        {
            "id": str(user_id),
            "email": payload.email,
            "hashed_password": hashed,
            "full_name": payload.full_name,
            "role": payload.role,
        },
    )
    await db.commit()

    token = create_access_token(user_id=user_id, role=payload.role)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expiry_seconds)
