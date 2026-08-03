from datetime import datetime,UTC
from uuid import UUID,uuid4

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped,mapped_column

from app.db.base_class import Base

def utc_now()->datetime:
    return datetime.now(UTC)

class BaseModel(Base):
    __abstract__=True

    id:Mapped[UUID]=mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    created_at:Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    updated_at:Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )