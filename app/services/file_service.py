from fastapi import UploadFile
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime,timezone

from ..db.models.file import File
from ..db.models.user import User
from ..repositories.file_repository import FileRepository
from ..repositories.folder_repository import FolderRepository
from ..services.storage_service import StorageService
from ..services.audit_service import AuditService
from ..services.PermissionService import PermissionService
from ..core.enum import AuditAction
from ..core.enum import ResourceType,PermissionRole
from ..schemas.file import FileRenameRequest,FileMoveRequest

from ..core.exceptions import FolderNotFound,StorageQuotaExceededException,DuplicateFileNameException

class FileService:
    def __init__(self,db:Session):
        self.db=db
        self.file_repository=FileRepository(db)
        self.folder_repository=FolderRepository(db)

        self.audit_service=AuditService(db)
        self.storage_service=StorageService()
        self.permission_service=PermissionService(db)

    def upload_file(
            self,
            *,
            upload_file:UploadFile,
            user:User,
            folder_id:UUID | None,
    ):
        if folder_id is not None:
            folder=self.folder_repository.get_by_id_and_user(
                folder_id=folder_id,
                user_id=user.id,
            )
            
            if folder is None:
                raise FolderNotFound()
            
        self.check_storage_quota(
            user=user,
            file_size=upload_file.size,
        )
            
            
        stored_name,storage_path=(
            self.storage_service.save_file(upload_file)
        )
        try:
            file=File(
                original_name=upload_file.filename,
                stored_name=stored_name,
                mime_type=upload_file.content_type,
                size=upload_file.size,
                storage_path=storage_path,
                user_id=user.id,
                folder_id=folder_id,
            )

            self.file_repository.create(file)

            user.storage_used+=upload_file.size

            self.audit_service.log(
                user=user,
                action=AuditAction.UPLOAD_FILE,
                file=file,
                folder=folder if folder_id else None,
                details=f"Uploaded '{file.original_name}'",
            )

            self.db.commit()
            self.db.refresh(file)

            return file

        except Exception:
            self.db.rollback()
            self.storage_service.delete_file(storage_path)
            raise

    
    def download_file(
            self,
            *,
            file_id:UUID,
            user:User,
    ):
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.VIEWER,
        )
        file=self.file_repository.get_by_id(id=file_id)

        if file is None:
            raise FileNotFoundError()
        
        path=self.storage_service.get_file_path(
            file.storage_path,
        )

        return file,path
    
    def rename_file(
            self,
            *,
            file_id:UUID,
            data:FileRenameRequest,
            user:User,
    )->File:
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.EDITOR,
        )

        file=self.file_repository.get_by_id(id=file_id)

        if file is None:
            raise FileNotFoundError()
        
        existing=self.file_repository.get_by_name_and_folder(
            name=data.name,
            folder_id=file.folder_id,
            user_id=file.user_id,
        )

        if existing is not None and existing.id != file.id:
            raise DuplicateFileNameException()
        
        if file.original_name==data.name:
            return file
        file.original_name=data.name
        self.audit_service.log(
          user=user,
          action=AuditAction.RENAME_FILE,
          file_id=file.id,
          details=f"Updated the File Name to {file.original_name}"
        )
        self.db.commit()
        self.db.refresh(file)
        return file
    
    def move_file(
            self,
            *,
            user:User,
            file_id:UUID,
            data:FileMoveRequest,
    ):
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.EDITOR,
        )

        if data.folder_id is not None:
            self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FOLDER,
            resource_id=data.folder_id,
            required_role=PermissionRole.EDITOR,
        )
            
        file=self.file_repository.get_by_id(id=file_id)

        if file is None:
            raise FileNotFoundError()
        
        if file.folder_id==data.folder_id:
            return file
        
        if data.folder_id is not None:
            folder=self.folder_repository.get_by_id(id=data.folder_id)

            if folder is None:
                raise FolderNotFound()
            
        existing=self.file_repository.get_by_name_and_folder(
            name=file.original_name,
            folder_id=data.folder_id,
            user_id=file.user_id,
        )

        if existing is not None and existing.id!=file.id:
            raise DuplicateFileNameException()
        
        file.folder_id=data.folder_id
        self.audit_service.log(
            user=user,
            action=AuditAction.MOVE_FILE,
            file_id=file.id,
            details=f"Moved {file.original_name} to folder {data.folder_id}",
        )
        self.db.commit()
        self.db.refresh(file)
        return File

    def delete_file(
            self,
            *,
            file_id:UUID,
            user:User,
    ):
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.EDITOR,
        )

        file=self.file_repository.get_by_id(id=file_id)

        if file is None:
            raise FileNotFoundError()

        file.is_deleted=True
        file.deleted_at=datetime.now(timezone.utc)

        self.audit_service.log(
          user=user,
          action=AuditAction.DELETE_FILE,
          file=file,
          folder=None,
          details=f"Moved '{file.original_name}' to recycle bin",
    )

        self.file_repository.update(file)

        self.db.commit()
        print("Commited")
        self.db.refresh(file)

    def restore_file(
            self,
            *,
            file_id:UUID,
            user:User
    ):
        file=self.file_repository.get_by_id(id=file_id)

        if not file.is_deleted:
            raise FileNotFoundError()

        if file is None:
            raise FileNotFoundError()
        
        file.is_deleted=False
        file.deleted_at=None

        self.audit_service.log(
         user=user,
         action=AuditAction.RESTORE_FILE,
         file=file,
         details=f"Restored '{file.original_name}'",
    )

        self.db.commit()
        self.db.refresh(file)

        return file
    
    def permanently_delete_file(
            self,
            *,
            file_id:UUID,
            user:User,
    ):
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.EDITOR,
        )

        file=self.file_repository.get_by_id(id=file_id)

        if file is None:
            raise FileNotFoundError()
        
        self.storage_service.delete_file(
            file.storage_path
        )

        user.storage_used=max(0,user.storage_used-file.size)

        self.file_repository.delete(file)

        self.audit_service.log(
          user=user,
          action=AuditAction.PERMANENT_DELETE_FILE,
          file=file,
          details=f"Permanently deleted '{file.original_name}'",
    )

        self.db.commit()

    def get_recycle_bin(
            self,
            *,
            user:User
    ):
        return self.file_repository.list_deleted_files(
            user_id=user.id,
        )
    
    def cleanup_expired_files(
            self,
    ):
        expired_files=(
            self.file_repository.get_expired_deleted_files()
        )

        for file in expired_files:
            self.storage_service.delete_file(
                file.storage_path
            )

            file.user.storage_used=max(0,file.user.storage_used-file.size)

            self.file_repository.delete(file)

        self.db.commit()

        return len(expired_files)
    
    def check_storage_quota(
        self,
        *,
        user:User,
        file_size:int,
    ):
        if user.storage_used+file_size>user.storage_limit:
            raise StorageQuotaExceededException()
        

        