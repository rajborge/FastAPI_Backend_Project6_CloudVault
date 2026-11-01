from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from ..core.enum import AuditAction, PermissionRole, ResourceType
from ..core.exceptions import (
    FolderAlreadyExists,
    FolderNotFound,
    InvalidFolderMoveException,
)
from ..db.models.folder import Folder
from ..db.models.user import User
from ..repositories.file_repository import FileRepository
from ..repositories.folder_repository import FolderRepository
from ..repositories.permisson_repository import PermissionRepository
from ..schemas.folder import FolderCreate, FolderMoveRequest, FolderUpdate
from ..services.PermissionService import PermissionService
from ..services.audit_service import AuditService


class FolderService:
    def __init__(self, db: Session):
        self.db = db
        self.folder_repository = FolderRepository(db)
        self.file_repository = FileRepository(db)
        self.permission_repository = PermissionRepository(db)
        self.audit_service = AuditService(db)
        self.permission_service = PermissionService(db)

    def create_folder(self, *, user: User, data: FolderCreate) -> Folder:
        owner_id = user.id
        parent = None

        if data.parent_id is not None:
            self.permission_service.check_permissions(
                user=user,
                resource_type=ResourceType.FOLDER,
                resource_id=data.parent_id,
                required_role=PermissionRole.EDITOR,
            )
            parent = self.folder_repository.get_by_id(id=data.parent_id)
            if parent is None:
                raise FolderNotFound()
            owner_id = parent.user_id

        if self.folder_repository.folder_exists(
            user_id=owner_id,
            parent_id=data.parent_id,
            name=data.name,
        ):
            raise FolderAlreadyExists()

        folder = Folder(
            name=data.name,
            user_id=owner_id,
            parent_id=data.parent_id,
        )
        self.folder_repository.create(folder)
        self.audit_service.log(
            user=user,
            action=AuditAction.CREATE_FOLDER,
            folder=folder,
            details=f"Created folder '{folder.name}'.",
        )
        self.db.commit()
        self.db.refresh(folder)
        return folder

    def get_folder(
        self,
        *,
        user: User,
        parent_id: UUID | None,
    ) -> list[Folder]:
        if parent_id is None:
            return self.folder_repository.get_children(
                parent_id=None,
                user_id=user.id,
            )

        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FOLDER,
            resource_id=parent_id,
            required_role=PermissionRole.VIEWER,
        )
        parent = self.folder_repository.get_by_id(id=parent_id)
        if parent is None:
            raise FolderNotFound()

        return self.folder_repository.get_children(
            parent_id=parent_id,
            user_id=parent.user_id,
        )

    def rename_folder(
        self,
        *,
        folder_id: UUID,
        data: FolderUpdate,
        user: User,
    ) -> Folder:
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FOLDER,
            resource_id=folder_id,
            required_role=PermissionRole.EDITOR,
        )
        folder = self.folder_repository.get_by_id(id=folder_id)
        if folder is None:
            raise FolderNotFound()

        if self.folder_repository.folder_exists_except(
            folder_id=folder_id,
            user_id=folder.user_id,
            parent_id=folder.parent_id,
            name=data.name,
        ):
            raise FolderAlreadyExists()

        old_name = folder.name
        folder.name = data.name
        self.folder_repository.update(folder)
        self.audit_service.log(
            user=user,
            action=AuditAction.RENAME_FOLDER,
            folder=folder,
            details=f"Renamed folder '{old_name}' to '{folder.name}'.",
        )
        self.db.commit()
        self.db.refresh(folder)
        return folder

    def move_folder(
        self,
        *,
        user: User,
        folder_id: UUID,
        data: FolderMoveRequest,
    ) -> Folder:
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FOLDER,
            resource_id=folder_id,
            required_role=PermissionRole.EDITOR,
        )

        folder = self.folder_repository.get_by_id(id=folder_id)
        if folder is None:
            raise FolderNotFound()

        if data.parent_id == folder.id:
            raise InvalidFolderMoveException()

        destination = None
        if data.parent_id is None and user.id != folder.user_id:
            self.permission_service.check_permissions(
                user=user,
                resource_type=ResourceType.FOLDER,
                resource_id=folder_id,
                required_role=PermissionRole.OWNER,
            )

        if data.parent_id is not None:
            self.permission_service.check_permissions(
                user=user,
                resource_type=ResourceType.FOLDER,
                resource_id=data.parent_id,
                required_role=PermissionRole.EDITOR,
            )
            destination = self.folder_repository.get_by_id(id=data.parent_id)
            if destination is None:
                raise FolderNotFound()
            if destination.user_id != folder.user_id:
                raise InvalidFolderMoveException()

            current = destination
            while current is not None:
                if current.id == folder.id:
                    raise InvalidFolderMoveException()
                if current.parent_id is None:
                    break
                current = self.folder_repository.get_by_id(id=current.parent_id)

        existing = self.folder_repository.get_by_name_and_parent(
            name=folder.name,
            parent_id=data.parent_id,
            user_id=folder.user_id,
        )
        if existing is not None and existing.id != folder.id:
            raise FolderAlreadyExists()

        old_parent_id = folder.parent_id
        folder.parent_id = data.parent_id
        self.audit_service.log(
            user=user,
            action=AuditAction.MOVE_FOLDER,
            folder=folder,
            details=(
                f"Moved folder '{folder.name}' from parent "
                f"{old_parent_id} to parent {data.parent_id}."
            ),
        )
        self.db.commit()
        self.db.refresh(folder)
        return folder

    def delete_folder(self, *, folder_id: UUID, user: User) -> None:
        # Folder deletion is owner-only because it removes the folder tree itself.
        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FOLDER,
            resource_id=folder_id,
            required_role=PermissionRole.OWNER,
        )
        folder = self.folder_repository.get_by_id(id=folder_id)
        if folder is None:
            raise FolderNotFound()

        tree = self._collect_tree(folder)
        folder_ids = [node.id for node in tree]
        now = datetime.now(timezone.utc)

        # Preserve file rows and storage objects: move files to trash and detach
        # them before the DB cascades the folder tree deletion.
        for node in tree:
            for file in self.file_repository.get_all_by_folder(folder_id=node.id):
                if not file.is_deleted:
                    file.is_deleted = True
                    file.deleted_at = now
                file.folder_id = None
                self.file_repository.update(file)

        self.permission_repository.delete_for_resources(
            resource_type=ResourceType.FOLDER,
            resource_ids=folder_ids,
        )

        deleted_name = folder.name
        self.audit_service.log(
            user=user,
            action=AuditAction.DELETE_FOLDER,
            details=(
                f"Deleted folder tree '{deleted_name}'. "
                "Contained files were moved to Trash."
            ),
        )
        self.folder_repository.delete(folder)
        self.db.commit()

    def get_folder_contents(
        self,
        *,
        folder_id: UUID | None,
        user: User,
    ) -> dict:
        if folder_id is None:
            return {
                "folders": self.folder_repository.get_by_parent(
                    parent_id=None,
                    user_id=user.id,
                ),
                "files": self.file_repository.get_by_folder(
                    folder_id=None,
                    user_id=user.id,
                ),
            }

        self.permission_service.check_permissions(
            user=user,
            resource_type=ResourceType.FOLDER,
            resource_id=folder_id,
            required_role=PermissionRole.VIEWER,
        )
        folder = self.folder_repository.get_by_id(id=folder_id)
        if folder is None:
            raise FolderNotFound()

        return {
            "folders": self.folder_repository.get_by_parent(
                parent_id=folder_id,
                user_id=folder.user_id,
            ),
            "files": self.file_repository.get_by_folder_any_owner(
                folder_id=folder_id,
            ),
        }

    def _collect_tree(self, folder: Folder) -> list[Folder]:
        result = [folder]
        children = self.folder_repository.get_by_parent(
            parent_id=folder.id,
            user_id=folder.user_id,
        )
        for child in children:
            result.extend(self._collect_tree(child))
        return result
