from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_permission
from shared.models import Permission, Role, User
from shared.utils import get_session

router = APIRouter(prefix="/users", tags=["users"])

DBSession = Annotated[Session, Depends(get_session)]


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None


@router.get("", dependencies=[require_permission(Permission.user_manage)])
def list_users(
    session: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = session.query(User)
    total = q.count()
    users = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [UserOut.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{user_id}", dependencies=[require_permission(Permission.user_manage)])
def get_user(user_id: str, session: DBSession):
    user = session.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)


@router.patch("/{user_id}", dependencies=[require_permission(Permission.user_manage)])
def update_user(user_id: str, body: UserUpdate, session: DBSession):
    user = session.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    session.commit()  # commit before responding so follow-up reads see it
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=204, dependencies=[require_permission(Permission.user_manage)])
def delete_user(user_id: str, session: DBSession):
    user = session.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(user)
    session.commit()
