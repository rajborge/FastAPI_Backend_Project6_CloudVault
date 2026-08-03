from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import Enum,ForeignKey,UniqueConstraint,Index
from sqlalchemy.orm import Mapped,mapped_column,relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from ...core.enum import PermissionRole,ResourceType
from .base_model import BaseModel

if TYPE_CHECKING:
    from .user import User


class Permission(BaseModel):
    __tablename__="permissions"

    __table_args__=(
        UniqueConstraint(
            "user_id",
            "resource_type",
            "resource_id",
            name="uq_permission_per_resource",
        ),
        Index(
            "ix_permission_resource",
            "resource_type",
            "resource_id",
        ),
    )

    user_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id",ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    resource_type:Mapped[ResourceType]=mapped_column(
        Enum(ResourceType),
        nullable=False,
    )

    resource_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    role:Mapped[PermissionRole]=mapped_column(
        Enum(PermissionRole),
        nullable=False,
    )

    user:Mapped["User"]=relationship(
        back_populates="permissions",
    )