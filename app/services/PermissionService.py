from uuid import UUID
from sqlalchemy import select, and_, or_
from ..db.models.file import File
from ..db.models.folder import Folder

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
        if role == PermissionRole.OWNER:
            raise HTTPException(
                422, "Ownership cannot be granted. Choose Viewer, Commenter, or Editor."
            )
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

        from ..db.models.collaboration import Notification

        self.db.add(
            Notification(
                user_id=target_user.id,
                file_id=resource_id if resource_type == ResourceType.FILE else None,
                kind="sharing",
                message=f"{getattr(actor, 'username', 'The owner')} shared an item with you as {role.value}.",
            )
        )
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
                return self.recipient_role(permission.role)
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
                return self.recipient_role(permission.role)
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
        permissions = self.permission_repository.get_permissions_for_resource(
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return [self.describe_permission(permission) for permission in permissions]

    @staticmethod
    def recipient_role(role):
        # Legacy delegated OWNER rows never transfer the resource's ownership.
        return PermissionRole.EDITOR if role == PermissionRole.OWNER else role

    def describe_permission(self, permission):
        person = self.user_repository.get_by_id(permission.user_id)
        return {
            "id": permission.id,
            "user_id": permission.user_id,
            "resource_type": permission.resource_type,
            "resource_id": permission.resource_id,
            "role": self.recipient_role(permission.role),
            "created_at": permission.created_at,
            "username": person.username if person else "Unavailable user",
            "email": person.email if person else None,
        }

    def resource_access(self, *, user, resource_type, resource_id):
        resource = (
            self.file_repository
            if resource_type == ResourceType.FILE
            else self.folder_repository
        ).get_by_id(id=resource_id)
        if resource is None or (
            resource_type == ResourceType.FILE
            and (resource.is_deleted or resource.version_of is not None)
        ):
            raise HTTPException(404, "Resource not found.")
        role = self.get_effective_permission(
            user=user, resource_type=resource_type, resource_id=resource_id
        )
        if role is None:
            raise HTTPException(403, "You no longer have access to this item.")
        owner = self.user_repository.get_by_id(resource.user_id)
        owns = resource.user_id == user.id
        file = resource_type == ResourceType.FILE
        clean = not file or resource.scan_status == "CLEAN"
        editable = role in {PermissionRole.OWNER, PermissionRole.EDITOR}
        return {
            "owner_id": resource.user_id,
            "owner_username": owner.username if owner else "Unavailable owner",
            "owner_email": owner.email if owner else None,
            "effective_role": role,
            "capabilities": {
                "can_download": file and clean,
                "can_preview": file
                and clean
                and resource.mime_type
                in {
                    "application/pdf",
                    "text/plain",
                    "image/png",
                    "image/jpeg",
                    "image/webp",
                },
                "can_comment": file and role != PermissionRole.VIEWER,
                "can_edit": editable,
                "can_manage_access": owns,
                "can_replace": owns and file and clean,
                "can_trash": file and editable,
                "can_delete_folder": owns and not file,
                "can_add_files": owns and not file,
            },
        }

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
        from ..db.models.collaboration import Notification

        self.db.add(
            Notification(
                user_id=permission.user_id,
                kind="sharing",
                message="The owner revoked your access to a shared item.",
            )
        )
        self.db.commit()

    def sharing_item(self, permission, recipient):
        file = permission.resource_type == ResourceType.FILE
        resource = (self.file_repository if file else self.folder_repository).get_by_id(
            id=permission.resource_id
        )
        if resource is None or (
            file and (resource.is_deleted or resource.version_of is not None)
        ):
            return None
        access = self.resource_access(
            user=recipient,
            resource_type=permission.resource_type,
            resource_id=resource.id,
        )
        return {
            "permission_id": permission.id,
            "resource_type": permission.resource_type,
            "resource_id": resource.id,
            "role": access["effective_role"],
            "name": resource.original_name if file else resource.name,
            "created_at": resource.created_at,
            "shared_at": permission.created_at,
            "recipient_id": recipient.id,
            "recipient_username": recipient.username,
            "recipient_email": recipient.email,
            "mime_type": resource.mime_type if file else None,
            "size": resource.size if file else None,
            "scan_status": resource.scan_status if file else None,
            "parent_id": resource.folder_id if file else resource.parent_id,
            **access,
        }

    def list_shared_with_me(self, *, user: User) -> list[dict]:
        permissions = self.permission_repository.get_permissions_for_user(
            user_id=user.id
        )
        return [
            item
            for permission in permissions
            if (item := self.sharing_item(permission, user)) is not None
        ]

    def list_shared_by_me(self, *, user: User) -> list[dict]:
        permissions = self.db.execute(
            select(Permission)
            .outerjoin(
                File,
                and_(
                    Permission.resource_type == ResourceType.FILE,
                    File.id == Permission.resource_id,
                ),
            )
            .outerjoin(
                Folder,
                and_(
                    Permission.resource_type == ResourceType.FOLDER,
                    Folder.id == Permission.resource_id,
                ),
            )
            .where(or_(File.user_id == user.id, Folder.user_id == user.id))
            .order_by(Permission.created_at.desc())
        ).scalars()
        result = []
        for permission in permissions:
            recipient = self.user_repository.get_by_id(permission.user_id)
            if (
                recipient
                and (item := self.sharing_item(permission, recipient)) is not None
            ):
                result.append(item)
        return result
