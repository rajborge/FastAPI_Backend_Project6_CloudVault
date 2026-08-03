from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey,String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped,mapped_column,relationship

from .base_model import BaseModel

if TYPE_CHECKING:
    from .user import User
    from .file import File

class Folder(BaseModel):
    __tablename__="folders"

    name:Mapped[str]=mapped_column(
        String(255),
        nullable=False,
    )

    user_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id",ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    parent_id:Mapped[UUID | None]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("folders.id",ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    user:Mapped["User"]=relationship(
        back_populates="folders",
    )

    parent:Mapped["Folder | None"]=relationship(
        remote_side="Folder.id",
        back_populates="children",
    )

    children:Mapped[list["Folder"]]=relationship(
        back_populates="parent",
    )

    files:Mapped["File"]=relationship(
        back_populates="folder",
        cascade="all,delete-orphan",
    )