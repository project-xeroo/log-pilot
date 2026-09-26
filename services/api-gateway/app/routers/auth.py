from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from app.config import settings
from shared.models import Role, User
from shared.utils import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

DBSession = Annotated[Session, Depends(get_session)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    email: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: Role = Role.viewer


@router.post("/token", response_model=TokenResponse)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: DBSession):
    user = session.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(
        {"sub": str(user.id), "role": user.role.value, "email": user.email}
    )
    return TokenResponse(
        access_token=token,
        role=user.role.value,
        user_id=str(user.id),
        email=user.email,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, session: DBSession):
    if session.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    session.add(user)
    session.flush()
    token = create_access_token(
        {"sub": str(user.id), "role": user.role.value, "email": user.email}
    )
    return TokenResponse(
        access_token=token,
        role=user.role.value,
        user_id=str(user.id),
        email=user.email,
    )


@router.get("/me")
def me(current_user: CurrentUser):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
    }
