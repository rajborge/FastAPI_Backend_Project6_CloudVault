from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..core.dependencies import get_current_user
from ..core.enum import ResourceType
from ..db.database import get_db
from ..db.models.user import User
from ..schemas.permission import (
    PermissionGrantRequest,
    PermissionResponse,
    SharedResourceResponse,
)
from ..services.PermissionService import PermissionService


router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.post("", response_model=PermissionResponse)
def grant_permission(
    data: PermissionGrantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return PermissionService(db).grant_permission(
        actor=current_user,
        target_user_id=data.target_user_id,
        target_identifier=data.target_identifier,
        resource_type=data.resource_type,
        resource_id=data.resource_id,
        role=data.role,
    )


@router.get("/shared-with-me", response_model=list[SharedResourceResponse])
def shared_with_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return PermissionService(db).list_shared_with_me(user=current_user)


@router.get("", response_model=list[PermissionResponse])
def list_permissions(
    resource_type: ResourceType,
    resource_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return PermissionService(db).list_permissions(
        actor=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
    )


@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_permission(
    permission_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    PermissionService(db).revoke_permission(
        permission_id=permission_id,
        actor=current_user,
    )
