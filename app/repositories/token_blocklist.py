from .base import BaseRepository
from ..db.models.token_blocklist import TokenBlocklist
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID

class TokenBlocklistRepository(BaseRepository[TokenBlocklist]):
    def __init__(self, db:Session):
        super().__init__(db, TokenBlocklist)

    def get_by_jti(self,jti:UUID)->TokenBlocklist | None:
        stmt=select(TokenBlocklist).where(TokenBlocklist.jti==jti)
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()
