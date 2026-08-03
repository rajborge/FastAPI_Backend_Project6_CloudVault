from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from datetime import datetime

from sqlalchemy import ForeignKey,String,BigInteger,DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped,mapped_column,relationship

from .base_model import BaseModel

if TYPE_CHECKING:
    from .user import User
    from .folder import Folder
    from .sharedFile import SharedFile

class File(BaseModel):
    __tablename__="files"

    original_name:Mapped[str]=mapped_column(
        String(255),
        nullable=False,
    )

    stored_name:Mapped[str]=mapped_column(
        String(255),
        nullable=False,
    )

    mime_type:Mapped[str]=mapped_column(
        String(100),
        nullable=False,
    )

    size:Mapped[int]=mapped_column(
        BigInteger,
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    user_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id",ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    folder_id:Mapped[UUID | None]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("folders.id",ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    is_deleted:Mapped[bool]=mapped_column(
        default=False,
        nullable=False,
    )

    deleted_at:Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user:Mapped["User"]=relationship(
        back_populates="files",
    )

    folder:Mapped["Folder | None"]=relationship(
        back_populates="files",
    )

    shared_links:Mapped[list["SharedFile"]]=relationship(
        back_populates="file",
        cascade="all,delete-orphan",
    )