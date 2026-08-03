from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.enum import PermissionRole
from ..core.enum import ResourceType
from ..db.models.permission import Permission

from .base import BaseRepository

class PermissionRepository(BaseRepository[Permission]):
    def __init__(self,db:Session):
        self.db=db

    def get_explicit_permission(
            self,
            *,
            user_id:UUID,
            resource_type:ResourceType,
            resource_id:UUID,
    )->Permission:
        stmt=(
            select(Permission)
            .where(
                Permission.user_id==user_id,
                Permission.resource_type==resource_type,
                Permission.resource_id==resource_id,
            )
        )
        result=self.db.execute(stmt)

        return result.scalar_one_or_none()
    
    def get_permissions_for_resource(
            self,
            *,
            resource_type:ResourceType,
            resource_id:UUID,
    )->list[Permission]:
        stmt=(
            select(Permission)
            .where(
                Permission.resource_type==resource_type,
                Permission.resource_id==resource_id,
            )
        )

        result=self.db.execute(stmt)

        return list(result.scalars().all())
    
    def get_permissions_for_user(
            self,
            *,
            user_id:UUID,
    )->list[Permission]:
        stmt=(
            select(Permission)
            .where(
                Permission.user_id==user_id,
            )
        )

        result=self.db.execute(stmt)

        return list(result.scalars().all())   