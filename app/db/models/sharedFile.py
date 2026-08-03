from uuid import UUID
from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Boolean,String,DateTime,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column,relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base_model import BaseModel

if TYPE_CHECKING:
    from .user import User
    from .file import File

class SharedFile(BaseModel):
    __tablename__="shared_files"

    token:Mapped[str]=mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    file_id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.id",ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_by:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id",ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    expires_at:Mapped[datetime | None]=mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    download_count:Mapped[int]=mapped_column(
        nullable=False,
        default=0,
    )

    is_active:Mapped[bool]=mapped_column(
        Boolean,
        default=True,
    )

    password_hash:Mapped[str | None]=mapped_column(
        String(255),
        nullable=True,
    )

    creator:Mapped["User"]=relationship(
        back_populates="shared_links",
    )

    file:Mapped["File"]=relationship(
        back_populates="shared_links",
    )

