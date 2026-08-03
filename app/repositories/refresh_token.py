from datetime import datetime,UTC
from uuid import UUID

from sqlalchemy import delete,select,update
from sqlalchemy.orm import Session

from ..db.models.refresh_token import RefreshToken
from .base import BaseRepository

class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self,db:Session):
        super().__init__(db,RefreshToken)

    def get_by_jti(
            self,
            jti:UUID,
    )->RefreshToken | None:
        stmt=select(RefreshToken).where(RefreshToken.jti==jti)
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    def revoke(
            self,
            refresh_token:RefreshToken,
    )->None:
        refresh_token.is_revoked=True
        self.db.commit()

    def delete_expired(self)->int:
        stmt=(
            delete(RefreshToken)
            .where(RefreshToken.expires_at<datetime.now(UTC))
        )
        result=self.db.execute(stmt)
        self.db.commit()
        return result.rowcount
    
    def revoke_by_jti(self,jti:UUID)->None:
        stmt=(
            update(RefreshToken)
            .where(RefreshToken.jti==jti)
            .values(is_revoked=True)
        )
        self.db.execute(stmt)