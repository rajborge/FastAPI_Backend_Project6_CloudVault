from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import Text,DateTime,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column,relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base_model import BaseModel
if TYPE_CHECKING:
    from .user import User

class AuditLog(BaseModel):
    __tablename__="audit_logs"

    user_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id",ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action:Mapped[str]=mapped_column(
        Text,
        nullable=False,
    )

    details:Mapped[str]=mapped_column(
        Text,
        nullable=False,
    )

    file_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.id",ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    folder_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("folders.id",ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    user:Mapped["User"]=relationship(
        back_populates="audit_logs",
    )

