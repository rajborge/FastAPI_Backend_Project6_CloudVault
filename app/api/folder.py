from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import Annotated
from uuid import UUID
from fastapi import Query

from app.core.dependencies import get_current_user
from app.db.models.user import User
from app.db.database import get_db
from app.schemas.folder import (
    FolderCreate,
    FolderResponse,
    FolderUpdate,
    FolderContentsResponse,
    FolderMoveRequest,
)
from app.services.folder_service import FolderService
from app.services.PermissionService import PermissionService
from app.core.enum import ResourceType
from app.schemas.file import FileResponse


def describe_contents(contents, user, db):
    permissions = PermissionService(db)
    return {
        kind: [
            {
                **schema.model_validate(item, from_attributes=True).model_dump(),
                **permissions.resource_access(
                    user=user, resource_type=resource_type, resource_id=item.id
                ),
            }
            for item in contents[kind]
        ]
        for kind, schema, resource_type in (
            ("files", FileResponse, ResourceType.FILE),
            ("folders", FolderResponse, ResourceType.FOLDER),
        )
    }


router = APIRouter(prefix="/folders", tags=["Folders"])


@router.post(
    "",
    response_model=FolderResponse,
)
def create_folder(
    data: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = FolderService(db)

    folder = service.create_folder(
        data=data,
        user=current_user,
    )
    return folder


@router.get(
    "",
    response_model=list[FolderResponse],
)
def get_folders(
    parent_id: Annotated[UUID | None, Query()] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = FolderService(db)

    return service.get_folder(
        user=current_user,
        parent_id=parent_id,
    )


@router.patch(
    "/{folder_id}",
    response_model=FolderResponse,
)
def rename_folder(
    folder_id: UUID,
    data: FolderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    service = FolderService(db)

    return service.rename_folder(
        folder_id=folder_id,
        data=data,
        user=current_user,
    )


@router.patch("/{folder_id}/move")
def move_folder(
    folder_id: UUID,
    data: FolderMoveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = FolderService(db)

    return service.move_folder(
        user=user,
        folder_id=folder_id,
        data=data,
    )


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = FolderService(db)

    service.delete_folder(
        folder_id=folder_id,
        user=current_user,
    )


@router.get(
    "/root",
    response_model=FolderContentsResponse,
)
def get_root_contents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = FolderService(db)

    return describe_contents(
        service.get_folder_contents(folder_id=None, user=current_user), current_user, db
    )


@router.get(
    "/{folder_id}/contents",
    response_model=FolderContentsResponse,
)
def get_folder_contents(
    folder_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = FolderService(db)

    return describe_contents(
        service.get_folder_contents(folder_id=folder_id, user=current_user),
        current_user,
        db,
    )
