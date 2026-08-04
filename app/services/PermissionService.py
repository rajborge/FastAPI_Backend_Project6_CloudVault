from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import status,HTTPException

from ..db.database import get_db
from ..core.dependencies import get_current_user

from ..db.models.permission import Permission
from ..db.models.user import User
from ..db.models.folder import Folder

from ..repositories.permisson_repository import PermissionRepository
from ..repositories.folder_repository import FolderRepository
from ..repositories.file_repository import FileRepository

from ..core.enum import ResourceType,PermissionRole

from ..core.exceptions import FolderNotFound

class PermissionService:
    def __init__(self,db:Session):
        self.db=db

        self.permission_repository=PermissionRepository(db)
        self.folder_repository=FolderRepository(db)
        self.file_repository=FileRepository(db)

    def grant_permission(
            self,
            *,
            user:User,
            resource_type:ResourceType,
            resource_id:UUID,
            role:PermissionRole,
    ):
        if resource_type == ResourceType.FILE:
            file=self.file_repository.get_by_id(id=resource_id)

            if file is None:
                raise FileNotFoundError()
            
        elif resource_type == ResourceType.FOLDER:
            folder=self.folder_repository.get_by_id(id=resource_id)

            if folder is None:
                raise FolderNotFound()
        
            permission=Permission(
                user_id=user.id,
                resource_type=resource_type,
                resource_id=resource_id,
                role=role,
            )

            self.permission_repository.create(permission)

            self.db.commit()

            self.db.refresh(permission)

            return permission
        
    
    def get_effective_permission(
            self,
            *,
            resource_type:ResourceType,
            resource_id:UUID,
            user:User,
    )->PermissionRole | None:
        if resource_type==ResourceType.FILE:
            file=self.file_repository.get_by_id(id=resource_id)

            if file is None:
                raise FileNotFoundError()
            
            if file.user_id==user.id:
                return PermissionRole.EDITOR
            
            permission=self.permission_repository.get_explicit_permission(
                user_id=user.id,
                resource_type=ResourceType.FILE,
                resource_id=resource_id,
            )

            if permission is not None:
                return permission.role
            
            if file.folder_id is None:
                return None
            
            current=self.folder_repository.get_by_id(id=file.folder_id)

        else:
            current=self.folder_repository.get_by_id(id=resource_id)

            if current is None:
                raise FolderNotFound()
            
            if current.user_id==user.id:
                return PermissionRole.EDITOR
            
        while current is not None:
            permission=self.permission_repository.get_explicit_permission(
                user_id=user.id,
                resource_type=ResourceType.FOLDER,
                resource_id=current.id,
            )

            if permission is not None:
                return permission.role
            
            if current.parent_id is None:
                break

            current=self.folder_repository.get_by_id(id=current.parent_id)

        return None
    
    
    def check_permissions(
            self,
            *,
            user:User,
            resource_type:ResourceType,
            resource_id:UUID,
            required_role:PermissionRole,      
    )->None:
        permission=self.get_effective_permission(
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        if permission is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission Denied."
            )
        PERMISSION_LEVEL={
            PermissionRole.VIEWER:1,
            PermissionRole.EDITOR:2,
        }

        if (
            PERMISSION_LEVEL[permission]<PERMISSION_LEVEL[required_role]
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission Denied."
            )