from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.enum import PermissionRole, ResourceType
from ..db.models.permission import Permission
from .base import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    def __init__(self, db: Session):
        super().__init__(db, Permission)

    def get_explicit_permission(
        self,
        *,
        user_id: UUID,
        resource_type: ResourceType,
        resource_id: UUID,
    ) -> Permission | None:
        stmt = select(Permission).where(
            Permission.user_id == user_id,
            Permission.resource_type == resource_type,
            Permission.resource_id == resource_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_permissions_for_resource(
        self,
        *,
        resource_type: ResourceType,
        resource_id: UUID,
    ) -> list[Permission]:
        stmt = select(Permission).where(
            Permission.resource_type == resource_type,
            Permission.resource_id == resource_id,
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_permissions_for_user(
        self,
        *,
        user_id: UUID,
    ) -> list[Permission]:
        stmt = (
            select(Permission)
            .where(Permission.user_id == user_id)
            .order_by(Permission.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def delete_for_resources(
        self,
        *,
        resource_type: ResourceType,
        resource_ids: list[UUID],
    ) -> int:
        if not resource_ids:
            return 0
        stmt = delete(Permission).where(
            Permission.resource_type == resource_type,
            Permission.resource_id.in_(resource_ids),
        )
        result = self.db.execute(stmt)
        return result.rowcount or 0
