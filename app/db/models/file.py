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

    version_of: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), index=True,
    )
    scan_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_lease: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    index_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    index_error: Mapped[str | None] = mapped_column(String(300))
    index_lease: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

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

    content_sha256:Mapped[str | None]=mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    storage_backend:Mapped[str]=mapped_column(
        String(20),
        default="local",
        nullable=False,
    )

    scan_status:Mapped[str]=mapped_column(
        String(20),
        default="PENDING_SCAN",
        nullable=False,
    )

    blob_id:Mapped[UUID | None]=mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("storage_blobs.id",ondelete="SET NULL"),
        nullable=True,
        index=True,
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
