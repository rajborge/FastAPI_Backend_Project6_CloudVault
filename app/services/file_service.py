import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.enum import AuditAction, PermissionRole, ResourceType
from ..core.exceptions import (
    DuplicateFileNameException,
    FileNotFoundException,
    FileNotReadyException,
    FolderNotFound,
    StorageQuotaExceededException,
)
from ..db.models.file import File
from ..db.models.user import User
from ..repositories.file_repository import FileRepository
from ..repositories.folder_repository import FolderRepository
from ..repositories.storage_blob_repository import StorageBlobRepository
from ..repositories.user import UserRepository
from ..schemas.file import FileMoveRequest, FileRenameRequest
from ..services.PermissionService import PermissionService
from ..services.audit_service import AuditService
from ..services.storage_service import StorageService
from ..tasks.file_task import enqueue_file_scan


logger = logging.getLogger("cloudvault.storage")


class FileService:
    def __init__(self, db: Session):
        self.db = db
        self.file_repository = FileRepository(db)
        self.storage_blob_repository = StorageBlobRepository(db)
        self.folder_repository = FolderRepository(db)
        self.user_repository = UserRepository(db)
        self.audit_service = AuditService(db)
        self.storage_service = StorageService()
        self.permission_service = PermissionService(db)

    def upload_file(
        self,
        *,
        upload_file: UploadFile,
        user: User,
        folder_id: UUID | None,
    ) -> File:
        folder = None
        if folder_id is not None:
            # Existing local-upload flow stays owner-scoped. Direct R2 upload is
            # the preferred path and can be extended for collaborative uploads later.
            folder = self.folder_repository.get_by_id_and_user(
                folder_id=folder_id,
                user_id=user.id,
            )
            if folder is None:
                raise FolderNotFound()

        locked_user = self.user_repository.get_by_id_for_update(user.id)
        if locked_user is None:
            raise FileNotFoundException()
        user = locked_user

        remaining_quota = user.storage_limit - user.storage_used - user.storage_reserved
        maximum_upload_size = min(
            settings.MAX_FILE_SIZE_MB * 1024 * 1024,
            remaining_quota,
        )
        if maximum_upload_size <= 0:
            raise StorageQuotaExceededException()

        self.check_storage_quota(
            user=user,
            file_size=upload_file.size or 0,
        )
        if upload_file.size is not None and upload_file.size > maximum_upload_size:
            raise StorageQuotaExceededException()

        stored_name, storage_path, file_size, content_sha256 = (
            self.storage_service.save_file(
                upload_file,
                max_bytes=maximum_upload_size,
            )
        )

        try:
            file = File(
                original_name=upload_file.filename,
                stored_name=stored_name,
                mime_type=upload_file.content_type or "application/octet-stream",
                size=file_size,
                storage_path=storage_path,
                content_sha256=content_sha256,
                user_id=user.id,
                folder_id=folder_id,
            )
            self.file_repository.create(file)
            user.storage_used += file_size
            self.audit_service.log(
                user=user,
                action=AuditAction.UPLOAD_FILE,
                file=file,
                folder=folder,
                details=f"Uploaded '{file.original_name}'.",
            )
            self.db.commit()
            self.db.refresh(file)
            enqueue_file_scan(file.id)
            return file
        except Exception:
            self.db.rollback()
            self.storage_service.delete_file(storage_path)
            raise

    def download_file(self, *, file_id: UUID, user: User):
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.VIEWER,
        )
        file = self.file_repository.get_by_id(id=file_id)
        if file is None or file.is_deleted:
            raise FileNotFoundException()
        if file.scan_status != "CLEAN":
            raise FileNotReadyException()

        self.audit_service.log(
            user=user,
            action=AuditAction.DOWNLOAD_FILE,
            file=file,
            details=f"Downloaded '{file.original_name}'.",
        )
        self.db.commit()

        if file.storage_backend == "r2":
            from .r2_storage_service import R2StorageService

            return file, R2StorageService().create_download_url(
                object_key=file.storage_path,
            )

        path = self.storage_service.get_file_path(file.storage_path)
        return file, path

    def rename_file(
        self,
        *,
        file_id: UUID,
        data: FileRenameRequest,
        user: User,
    ) -> File:
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.EDITOR,
        )
        file = self.file_repository.get_by_id(id=file_id)
        if file is None or file.is_deleted:
            raise FileNotFoundException()

        existing = self.file_repository.get_by_name_and_folder(
            name=data.name,
            folder_id=file.folder_id,
            user_id=file.user_id,
        )
        if existing is not None and existing.id != file.id:
            raise DuplicateFileNameException()
        if file.original_name == data.name:
            return file

        old_name = file.original_name
        file.original_name = data.name
        self.audit_service.log(
            user=user,
            action=AuditAction.RENAME_FILE,
            file=file,
            details=f"Renamed file '{old_name}' to '{file.original_name}'.",
        )
        self.db.commit()
        self.db.refresh(file)
        return file

    def move_file(
        self,
        *,
        user: User,
        file_id: UUID,
        data: FileMoveRequest,
    ) -> File:
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.EDITOR,
        )
        file = self.file_repository.get_by_id(id=file_id)
        if file is None or file.is_deleted:
            raise FileNotFoundException()
        if file.folder_id == data.folder_id:
            return file

        if data.folder_id is None and user.id != file.user_id:
            self.permission_service.check_permissions(
                user=user,
                resource_type=ResourceType.FILE,
                resource_id=file_id,
                required_role=PermissionRole.OWNER,
            )

        if data.folder_id is not None:
            self.permission_service.check_permissions(
                user=user,
                resource_type=ResourceType.FOLDER,
                resource_id=data.folder_id,
                required_role=PermissionRole.EDITOR,
            )
            folder = self.folder_repository.get_by_id(id=data.folder_id)
            if folder is None:
                raise FolderNotFound()
            # Avoid creating cross-owner folder/file trees that the current
            # ownership-based quota and listing model cannot represent safely.
            if folder.user_id != file.user_id:
                raise FolderNotFound()

        existing = self.file_repository.get_by_name_and_folder(
            name=file.original_name,
            folder_id=data.folder_id,
            user_id=file.user_id,
        )
        if existing is not None and existing.id != file.id:
            raise DuplicateFileNameException()

        old_folder_id = file.folder_id
        file.folder_id = data.folder_id
        self.audit_service.log(
            user=user,
            action=AuditAction.MOVE_FILE,
            file=file,
            details=(
                f"Moved '{file.original_name}' from folder {old_folder_id} "
                f"to folder {data.folder_id}."
            ),
        )
        self.db.commit()
        self.db.refresh(file)
        return file

    def delete_file(self, *, file_id: UUID, user: User) -> None:
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            required_role=PermissionRole.EDITOR,
        )
        file = self.file_repository.get_by_id(id=file_id)
        if file is None or file.is_deleted:
            raise FileNotFoundException()

        file.is_deleted = True
        file.deleted_at = datetime.now(timezone.utc)
        self.audit_service.log(
            user=user,
            action=AuditAction.DELETE_FILE,
            file=file,
            details=f"Moved '{file.original_name}' to Trash.",
        )
        self.file_repository.update(file)
        self.db.commit()
        self.db.refresh(file)

    def restore_file(self, *, file_id: UUID, user: User) -> File:
        # Restore is owner-scoped. This closes the previous IDOR where a generic
        # get_by_id allowed another authenticated user to restore a known UUID.
        file = self.file_repository.get_deleted_by_id_and_user(
            file_id=file_id,
            user_id=user.id,
        )
        if file is None:
            raise FileNotFoundException()

        existing = self.file_repository.get_by_name_and_folder(
            name=file.original_name,
            folder_id=file.folder_id,
            user_id=user.id,
        )
        if existing is not None and existing.id != file.id:
            raise DuplicateFileNameException()

        file.is_deleted = False
        file.deleted_at = None
        self.audit_service.log(
            user=user,
            action=AuditAction.RESTORE_FILE,
            file=file,
            details=f"Restored '{file.original_name}'.",
        )
        self.db.commit()
        self.db.refresh(file)
        return file

    def permanently_delete_file(self, *, file_id: UUID, user: User) -> None:
        # Permanent delete is deliberately owner-only and only operates on Trash.
        file = self.file_repository.get_deleted_by_id_and_user(
            file_id=file_id,
            user_id=user.id,
        )
        if file is None:
            raise FileNotFoundException()

        payload_to_delete = self.storage_blob_repository.release_file_reference(file)
        file.user.storage_used = max(0, file.user.storage_used - file.size)

        # Log without a file FK; audit FK uses SET NULL in the new migration,
        # but avoiding the FK here also preserves the event on immediate delete.
        self.audit_service.log(
            user=user,
            action=AuditAction.PERMANENT_DELETE_FILE,
            details=f"Permanently deleted '{file.original_name}'.",
        )
        self.file_repository.delete(file)
        self.db.commit()
        self._delete_payload_reference(payload_to_delete)

    def get_recycle_bin(self, *, user: User):
        return self.file_repository.list_deleted_files(user_id=user.id)

    def cleanup_expired_files(self, *, user: User | None = None) -> int:
        expired_files = self.file_repository.get_expired_deleted_files(
            user_id=user.id if user is not None else None,
        )
        payloads_to_delete: list[tuple[str, str]] = []

        for file in expired_files:
            payload_to_delete = self.storage_blob_repository.release_file_reference(file)
            if payload_to_delete is not None:
                payloads_to_delete.append(payload_to_delete)
            file.user.storage_used = max(0, file.user.storage_used - file.size)
            self.file_repository.delete(file)

        self.db.commit()
        for payload in payloads_to_delete:
            self._delete_payload_reference(payload)
        return len(expired_files)

    def _delete_payload_reference(self, payload: tuple[str, str] | None) -> None:
        if payload is None:
            return
        storage_backend, storage_path = payload
        try:
            if storage_backend == "r2":
                from .r2_storage_service import R2StorageService

                R2StorageService().delete_object(object_key=storage_path)
                return
            self.storage_service.delete_file(storage_path)
        except Exception:
            logger.exception(
                "Failed to remove unreferenced payload: %s",
                storage_path,
            )

    def check_storage_quota(self, *, user: User, file_size: int) -> None:
        if user.storage_used + user.storage_reserved + file_size > user.storage_limit:
            raise StorageQuotaExceededException()
