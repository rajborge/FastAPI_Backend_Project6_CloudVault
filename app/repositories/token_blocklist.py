from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .base import BaseRepository
from ..db.models.token_blocklist import (
    TokenBlocklist,
)


class TokenBlocklistRepository(
    BaseRepository[TokenBlocklist]
):
    def __init__(
        self,
        db: Session,
    ):
        super().__init__(
            db,
            TokenBlocklist,
        )

    def get_by_jti(
        self,
        jti: UUID,
    ) -> TokenBlocklist | None:
        stmt = select(
            TokenBlocklist
        ).where(
            TokenBlocklist.jti == jti
        )

        result = self.db.execute(
            stmt
        )

        return result.scalar_one_or_none()

    def delete_expired(
        self,
    ) -> int:
        stmt = delete(
            TokenBlocklist
        ).where(
            TokenBlocklist.expires_at
            < datetime.now(UTC)
        )

        result = self.db.execute(
            stmt
        )

        return result.rowcount or 0