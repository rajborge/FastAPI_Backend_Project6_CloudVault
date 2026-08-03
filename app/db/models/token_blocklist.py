from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped,mapped_column

from .base_model import BaseModel

class TokenBlocklist(BaseModel):
    __tablename__="token_blocklist"

    jti:Mapped[UUID]=mapped_column(
        unique=True,
        nullable=False,
        index=True,
    )

    expires_at:Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )