from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from ..repositories.folder_repository import FolderRepository
from ..repositories.file_repository import FileRepository
from ..db.models.folder import Folder
from ..schemas.folder import FolderCreate,FolderResponse,FolderUpdate,FolderMoveRequest
from ..core.exceptions import FolderAlreadyExists,FolderNotFound,InvalidFolderMoveException
from ..db.models.user import User
from ..core.enum import AuditAction,ResourceType,PermissionRole
from ..services.audit_service import AuditService
from ..services.PermissionService import PermissionService

class FolderService:
    def __init__(self,db:Session):
        self.db=db
        self.folder_repository=FolderRepository(db)
        self.file_repository=FileRepository(db)

        self.audit_service=AuditService(db)
        self.permission_service=PermissionService(db)

    def create_folder(
            self,
            user:User,
            data:FolderCreate,
            ):
        if self.folder_repository.folder_exists(
            user_id=user.id,
            parent_id=data.parent_id,
            name=data.name,
        ):
            raise FolderAlreadyExists()
        
        if data.parent_id is not None:
            parent=self.folder_repository.get_by_id_and_user(
                folder_id=data.parent_id,
                user_id=user.id,
            )
            if parent is None:
                raise FolderNotFound()
         
        folder=Folder(
            name=data.name,
            user_id=user.id,
            parent_id=data.parent_id,
        )
        folder=self.folder_repository.create(folder)
        self.audit_service.log(
            user=user,
            action=AuditAction.CREATE_FOLDER,
            folder=folder,
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
    
    def move_folder(
            self,
            *,
            user:User,
            folder_id:UUID,
            data:FolderMoveRequest,
    ):
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FOLDER,
            resource_id=folder_id,
            required_role=PermissionRole.EDITOR,
        )

        folder=self.folder_repository.get_by_id(id=folder_id)   
        if folder is None:
            raise FolderNotFound()
        
        if data.parent_id==folder.id:
            raise InvalidFolderMoveException()

        if data.parent_id is not None:
            self.permission_service.check_permissions(
                user=user,
                resource_type=ResourceType.FOLDER,
                resource_id=data.parent_id,
                required_role=PermissionRole.EDITOR,
            )
        
            destination=self.folder_repository.get_by_id(id=data.parent_id)

            if destination is None:
                raise FolderNotFound()
        
            current = destination
            while current is not None:
                if current.id == folder.id:
                    raise InvalidFolderMoveException()

                if current.parent_id is None:
                    break

                current = self.folder_repository.get_by_id(
                id=current.parent_id,
                )

        existing = self.folder_repository.get_by_name_and_parent(
        name=folder.name,
        parent_id=data.parent_id,
        user_id=folder.user_id,
        )

        if existing is not None and existing.id != folder.id:
            raise FolderAlreadyExists()

        old_parent_id=folder.parent_id
        folder.parent_id = data.parent_id

        self.audit_service.log(
        user=user,
        action=AuditAction.MOVE_FOLDER,
        folder=folder,
        details=(
        f"Moved folder '{folder.name}' "
        f"from parent {old_parent_id} "
        f"to parent {data.parent_id}"
        ),
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
