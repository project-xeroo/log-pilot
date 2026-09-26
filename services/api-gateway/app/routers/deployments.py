from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_permission
from shared.models import DeploymentSnapshot, Permission
from shared.utils import get_session

router = APIRouter(prefix="/deployments", tags=["deployments"])

DBSession = Annotated[Session, Depends(get_session)]


class DeploymentIn(BaseModel):
    service_name: str
    environment: str = "production"
    version: str
    deployed_by: str | None = None
    deployed_at: datetime
    config_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class DeploymentOut(BaseModel):
    id: str
    service_name: str
    environment: str
    version: str
    deployed_by: str | None
    deployed_at: datetime
    config_snapshot: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ComparisonResult(BaseModel):
    base: DeploymentOut
    head: DeploymentOut
    config_diff: dict[str, Any]          # {key: {base: v, head: v}} for changed keys
    version_changed: bool
    deployer_changed: bool
    time_between_seconds: float


@router.post(
    "",
    response_model=DeploymentOut,
    status_code=201,
    dependencies=[require_permission(Permission.deployment_read)],
)
def record_deployment(body: DeploymentIn, session: DBSession):
    snap = DeploymentSnapshot(
        service_name=body.service_name,
        environment=body.environment,
        version=body.version,
        deployed_by=body.deployed_by,
        deployed_at=body.deployed_at,
        config_snapshot=body.config_snapshot,
        metadata_=body.metadata,
    )
    session.add(snap)
    session.flush()
    return DeploymentOut.model_validate(snap)


@router.get(
    "",
    dependencies=[require_permission(Permission.deployment_read)],
)
def list_deployments(
    session: DBSession,
    service_name: str | None = None,
    environment: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = session.query(DeploymentSnapshot)
    if service_name:
        q = q.filter(DeploymentSnapshot.service_name == service_name)
    if environment:
        q = q.filter(DeploymentSnapshot.environment == environment)
    q = q.order_by(DeploymentSnapshot.deployed_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [DeploymentOut.model_validate(d) for d in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/compare",
    response_model=ComparisonResult,
    dependencies=[require_permission(Permission.deployment_compare)],
)
def compare_deployments(
    base_id: str,
    head_id: str,
    session: DBSession,
):
    """Return a structured diff between two deployment snapshots."""
    base = session.get(DeploymentSnapshot, uuid.UUID(base_id))
    head = session.get(DeploymentSnapshot, uuid.UUID(head_id))
    if not base or not head:
        raise HTTPException(status_code=404, detail="One or both deployments not found")

    base_cfg: dict = base.config_snapshot or {}
    head_cfg: dict = head.config_snapshot or {}
    all_keys = set(base_cfg) | set(head_cfg)
    config_diff = {
        k: {"base": base_cfg.get(k), "head": head_cfg.get(k)}
        for k in all_keys
        if base_cfg.get(k) != head_cfg.get(k)
    }

    delta = abs((head.deployed_at - base.deployed_at).total_seconds())

    return ComparisonResult(
        base=DeploymentOut.model_validate(base),
        head=DeploymentOut.model_validate(head),
        config_diff=config_diff,
        version_changed=base.version != head.version,
        deployer_changed=base.deployed_by != head.deployed_by,
        time_between_seconds=delta,
    )


@router.get(
    "/{deployment_id}",
    response_model=DeploymentOut,
    dependencies=[require_permission(Permission.deployment_read)],
)
def get_deployment(deployment_id: str, session: DBSession):
    dep = session.get(DeploymentSnapshot, uuid.UUID(deployment_id))
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return DeploymentOut.model_validate(dep)
