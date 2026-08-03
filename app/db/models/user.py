from app.db.models.base_model import BaseModel

from datetime import datetime
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import Boolean,String,Enum,DateTime,BigInteger
from sqlalchemy.orm import Mapped,mapped_column,relationship

from ...core.enum import AuthProvider
from .folder import Folder
from ...core.constants import FREE_STORAGE_LIMIT

if TYPE_CHECKING:
    from .refresh_token import RefreshToken
    from .file import File
    from .auditlog import AuditLog
    from .sharedFile import SharedFile
    from .permission import Permission


class User(BaseModel):
    __tablename__="users"

    username:Mapped[str]=mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    email:Mapped[str]=mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    hashed_password:Mapped[str | None]=mapped_column(
        String(255),
        nullable=True,
    )

    auth_provider:Mapped[AuthProvider]=mapped_column(
        Enum(
            AuthProvider,
            values_callable=lambda enum:[e.value for e in enum],
            name="auth_provider_enum"
            ),
        default=AuthProvider.LOCAL,
        nullable=False,
    )

    provider_user_id:Mapped[str | None]=mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    is_verified:Mapped[bool]=mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_active:Mapped[bool]=mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    last_login_at:Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    refresh_tokens:Mapped[list["RefreshToken"]]=relationship(
        back_populates="user",
        cascade="all,delete-orphan",
    )

    folders:Mapped["Folder"]=relationship(
        back_populates="user",
        cascade="all,delete-orphan",
    )

    files:Mapped[list["File"]]=relationship(
        back_populates="user",
        cascade="all,delete-orphan",
    )

    shared_links:Mapped[list["SharedFile"]]=relationship(
        back_populates="creator",
        cascade="all,delete-orphan",
    )

    permissions:Mapped[list["Permission"]]=relationship(
        back_populates="user",
        cascade="all,delete-orphan",   
    )

    audit_logs:Mapped[list["AuditLog"]]=relationship(
        back_populates="user",
    )

    storage_used:Mapped[int]=mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    storage_limit:Mapped[int]=mapped_column(
        BigInteger,
        default=FREE_STORAGE_LIMIT,
        nullable=False,
    )