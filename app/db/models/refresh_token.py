from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean,String,DateTime,ForeignKey
from sqlalchemy.orm import mapped_column,Mapped,relationship
from typing import TYPE_CHECKING

from .base_model import BaseModel

if TYPE_CHECKING:
    from .user import User

class RefreshToken(BaseModel):
    __tablename__="refresh_tokens"

    user_id:Mapped[UUID]=mapped_column(
        ForeignKey("users.id",ondelete="CASCADE"),
        nullable=False,
    )

    jti:Mapped[UUID]=mapped_column(
        unique=True,
        nullable=False,
        index=True,
    )

    expires_at:Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    is_revoked:Mapped[bool]=mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    user:Mapped["User"]=relationship(
        back_populates="refresh_tokens",
    )