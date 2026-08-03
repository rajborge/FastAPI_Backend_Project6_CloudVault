from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from .base import BaseRepository
from ..db.models.sharedFile import SharedFile

class SharedFileRepository(BaseRepository[SharedFile]):
    def __init__(self, db:Session):
        super().__init__(db,SharedFile)

    def token_exists(
        self,
        token:str,
    )->bool:
        stmt=(
            select(SharedFile)
            .where(SharedFile.token==token)
        )
        result=self.db.execute(stmt)

        return result.scalar_one_or_none() is not None

    def get_by_token(
        self,
        *,
        token:str,
    )->SharedFile | None:
        stmt=(
            select(SharedFile)
            .where(SharedFile.token==token)
        )

        result=self.db.execute(stmt)
        return result.scalar_one_or_none()

        