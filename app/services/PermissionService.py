from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..core.enum import PermissionRole, ResourceType
from ..core.exceptions import (
    FileNotFoundException,
    FolderNotFound,
    PermissionNotFoundException,
    UserNotFoundException,
)
from ..db.models.permission import Permission
from ..db.models.user import User
from ..repositories.file_repository import FileRepository
from ..repositories.folder_repository import FolderRepository
from ..repositories.permisson_repository import PermissionRepository
from ..repositories.user import UserRepository


class PermissionService:
    def __init__(self, db: Session):
        self.db = db
        self.permission_repository = PermissionRepository(db)
        self.folder_repository = FolderRepository(db)
        self.file_repository = FileRepository(db)
        self.user_repository = UserRepository(db)

    def grant_permission(
        self,
        *,
        actor: User,
        target_user_id: UUID | None = None,
        target_identifier: str | None = None,
        resource_type: ResourceType,
        resource_id: UUID,
        role: PermissionRole,
    ):
        self.check_permissions(
            user=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            required_role=PermissionRole.OWNER,
        )

        target_user = None

        # Keep support for the original UUID-based API.
        if target_user_id is not None:
            target_user = self.user_repository.get_by_id(target_user_id)

        # New UI: accept username, email, or UUID as one friendly field.
        if target_user is None and target_identifier:
            identifier = target_identifier.strip()

            try:
                parsed_id = UUID(identifier)
            except (ValueError, TypeError, AttributeError):
                parsed_id = None

            if parsed_id is not None:
                target_user = self.user_repository.get_by_id(parsed_id)

            if target_user is None:
                target_user = self.user_repository.get_by_identifier(identifier)

        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Enter an existing username, email, or user ID.",
            )

        if target_user.id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already own this resource; you do not need to grant access to yourself.",
            )

        permission = self.permission_repository.get_explicit_permission(
            user_id=target_user.id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        if permission is None:
            permission = Permission(
                user_id=target_user.id,
                resource_type=resource_type,
                resource_id=resource_id,
                role=role,
            )
            self.permission_repository.create(permission)
        else:
            permission.role = role

        self.db.commit()
        self.db.refresh(permission)
        return permission

    def get_effective_permission(
        self,
        *,
        resource_type: ResourceType,
        resource_id: UUID,
        user: User,
    ) -> PermissionRole | None:
        if resource_type == ResourceType.FILE:
            file = self.file_repository.get_by_id(id=resource_id)
            if file is None:
                raise FileNotFoundException()
            if file.user_id == user.id:
                return PermissionRole.OWNER

            permission = self.permission_repository.get_explicit_permission(
                user_id=user.id,
                resource_type=ResourceType.FILE,
                resource_id=resource_id,
            )
            if permission is not None:
                return permission.role
            if file.folder_id is None:
                return None
            current = self.folder_repository.get_by_id(id=file.folder_id)
        else:
            current = self.folder_repository.get_by_id(id=resource_id)
            if current is None:
                raise FolderNotFound()
            if current.user_id == user.id:
                return PermissionRole.OWNER

        while current is not None:
            permission = self.permission_repository.get_explicit_permission(
                user_id=user.id,
                resource_type=ResourceType.FOLDER,
                resource_id=current.id,
            )
            if permission is not None:
                return permission.role
            if current.parent_id is None:
                break
            current = self.folder_repository.get_by_id(id=current.parent_id)

        return None

    def check_permissions(
        self,
        *,
        user: User,
        resource_type: ResourceType,
        resource_id: UUID,
        required_role: PermissionRole,
    ) -> None:
        permission = self.get_effective_permission(
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if permission is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission Denied.",
            )

        role_capabilities = {
            PermissionRole.VIEWER: {PermissionRole.VIEWER},
            PermissionRole.COMMENTER: {
                PermissionRole.VIEWER,
                PermissionRole.COMMENTER,
            },
            PermissionRole.EDITOR: {
                PermissionRole.VIEWER,
                PermissionRole.COMMENTER,
                PermissionRole.EDITOR,
            },
            PermissionRole.OWNER: {
                PermissionRole.VIEWER,
                PermissionRole.COMMENTER,
                PermissionRole.EDITOR,
                PermissionRole.OWNER,
            },
        }
        if required_role not in role_capabilities[permission]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission Denied.",
            )

    def list_permissions(
        self,
        *,
        actor: User,
        resource_type: ResourceType,
        resource_id: UUID,
    ):
        self.check_permissions(
            user=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            required_role=PermissionRole.OWNER,
        )
        return self.permission_repository.get_permissions_for_resource(
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def revoke_permission(self, *, permission_id: UUID, actor: User) -> None:
        permission = self.permission_repository.get_by_id(permission_id)
        if permission is None:
            raise PermissionNotFoundException()
        self.check_permissions(
            user=actor,
            resource_type=permission.resource_type,
            resource_id=permission.resource_id,
            required_role=PermissionRole.OWNER,
        )
        self.permission_repository.delete(permission)
        self.db.commit()

    def list_shared_with_me(self, *, user: User) -> list[dict]:
        results: list[dict] = []
        permissions = self.permission_repository.get_permissions_for_user(
            user_id=user.id
        )
        for permission in permissions:
            if permission.resource_type == ResourceType.FOLDER:
                folder = self.folder_repository.get_by_id(id=permission.resource_id)
                if folder is None:
                    continue
                results.append(
                    {
                        "permission_id": permission.id,
                        "resource_type": ResourceType.FOLDER,
                        "resource_id": folder.id,
                        "role": permission.role,
                        "name": folder.name,
                        "owner_id": folder.user_id,
                        "created_at": folder.created_at,
                        "parent_id": folder.parent_id,
                    }
                )
                continue

            file = self.file_repository.get_by_id(id=permission.resource_id)
            if file is None or file.is_deleted:
                continue
            results.append(
                {
                    "permission_id": permission.id,
                    "resource_type": ResourceType.FILE,
                    "resource_id": file.id,
                    "role": permission.role,
                    "name": file.original_name,
                    "owner_id": file.user_id,
                    "created_at": file.created_at,
                    "mime_type": file.mime_type,
                    "size": file.size,
                    "scan_status": file.scan_status,
                    "parent_id": file.folder_id,
                }
            )
        return results
