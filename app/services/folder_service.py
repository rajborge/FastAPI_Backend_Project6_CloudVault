from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from ..repositories.folder_repository import FolderRepository
from ..repositories.file_repository import FileRepository
from ..db.models.folder import Folder
from ..schemas.folder import FolderCreate,FolderResponse,FolderUpdate
from ..core.exceptions import FolderAlreadyExists,FolderNotFound
from ..db.models.user import User
from ..core.enum import AuditAction
from ..services.audit_service import AuditService

class FolderService:
    def __init__(self,db:Session):
        self.db=db
        self.folder_repository=FolderRepository(db)
        self.file_repository=FileRepository(db)

        self.audit_service=AuditService(db)

    def create_folder(
            self,
            user_id:UUID,
            data:FolderCreate,
            ):
        if self.folder_repository.folder_exists(
            user_id=user_id,
            parent_id=data.parent_id,
            name=data.name,
        ):
            raise FolderAlreadyExists()
        
        if data.parent_id is not None:
            parent=self.folder_repository.get_by_id_and_user(
                folder_id=data.parent_id,
                user_id=user_id,
            )
            if parent is None:
                raise FolderNotFound()
         
        folder=Folder(
            name=data.name,
            user_id=user_id,
            parent_id=data.parent_id,
        )
        folder=self.folder_repository.create(folder)
        self.audit_service.log(
            user_id=user_id,
            action=AuditAction.CREATE_FOLDER,
            folder_id=folder.id,
            details=f"Created {folder.name}."
        )
        self.db.commit()
        self.db.refresh(folder)
        return folder
    
    def get_folder(
        self,
        *,
        user:User,
        parent_id:UUID | None,
    )->list[Folder]:
        if parent_id is not None:
            parent=self.folder_repository.get_by_id_and_user(
                folder_id=parent_id,
                user_id=user.id,
            )

            if parent is None:
                raise FolderNotFound()
            
        return self.folder_repository.get_children(
            parent_id=parent_id,
            user_id=user.id,
        )
    
    def rename_folder(
            self,
            *,
            folder_id:UUID,
            data:FolderUpdate,
            user:User,
    )->Folder:
        folder=self.folder_repository.get_by_id_and_user(
            folder_id=folder_id,
            user_id=user.id,
        )

        if folder is None:
            raise FolderNotFound()
        
        if self.folder_repository.folder_exists_except(
            folder_id=folder_id,
            user_id=user.id,
            parent_id=folder.parent_id,
            name=data.name,
        ):
            raise FolderAlreadyExists()
        
        folder.name=data.name
        self.folder_repository.update(folder)
        self.audit_service.log(
        user=user,
        action=AuditAction.RENAME_FOLDER,
        folder_id=folder.id,
        details=f"Updated the filename to {folder.name}."
    )
        self.db.commit()
        self.db.refresh(folder)
        return folder
    
    def delete_folder(
            self,
            *,
            folder_id:UUID,
            user:User,
    ):
        folder=self.folder_repository.get_by_id_and_user(
            folder_id=folder_id,
            user_id=user.id,
        )

        if folder is None:
            raise FolderNotFound()
        
        self.folder_repository.delete(folder)
        self.audit_service.log(
        user=user,
        action=AuditAction.DELETE_FOLDER,
        folder_id=folder.id,
        details=f"Deleted Folder {folder.name}."
    )
        self.db.commit()

    def get_folder_contents(
            self,
            *,
            folder_id:UUID | None,
            user:User,
    ):
        if folder_id is not None:
            folder=self.folder_repository.get_by_id_and_user(
                folder_id=folder_id,
                user_id=user.id,
            )

            if folder is None:
                raise FolderNotFound()
            
        folders = self.folder_repository.get_by_parent(
        parent_id=folder_id,
        user_id=user.id,
    )

        files = self.file_repository.get_by_folder(
        folder_id=folder_id,
        user_id=user.id,
)

        return {
       "folders": folders,
        "files": files,
    }            
