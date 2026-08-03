from fastapi import APIRouter,Depends,status
from sqlalchemy.orm import Session
from typing import Annotated
from uuid import UUID
from fastapi import Query

from app.core.dependencies import get_current_user
from app.db.models.user import User
from app.db.database import get_db
from app.schemas.folder import FolderCreate,FolderResponse,FolderUpdate,FolderContentsResponse
from app.services.folder_service import FolderService

router=APIRouter(
    prefix="/folders",
    tags=["Folders"]
)

@router.post(
    "",
    response_model=FolderResponse,
)
def create_folder(
    data:FolderCreate,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FolderService(db)

    folder=service.create_folder(
        data=data,
        user_id=current_user.id,
    )
    return folder

@router.get(
    "",
    response_model=list[FolderResponse],
)
def get_folders(
    parent_id:Annotated[UUID | None,Query()]=None,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FolderService(db)

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

@router.delete("/{folder_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id:UUID,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FolderService(db)

    service.delete_folder(
        folder_id=folder_id,
        user=current_user,
    )

@router.get(
    "/root",
    response_model=FolderContentsResponse,
)
def get_root_contents(
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FolderService(db)

    return service.get_folder_contents(
        folder_id=None,
        user=current_user,
    )

@router.get(
    "/{folder_id}/contents",
    response_model=FolderContentsResponse,
)
def get_folder_contents(
    folder_id:UUID,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FolderService(db)

    return service.get_folder_contents(
        folder_id=folder_id,
        user=current_user,
    )