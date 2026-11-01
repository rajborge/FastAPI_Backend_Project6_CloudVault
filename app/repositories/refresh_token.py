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

    def get_by_jti_for_update(self, jti: UUID) -> RefreshToken | None:
        return self.db.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
            .with_for_update().execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def revoke_all_for_user(self, user_id: UUID) -> None:
        self.db.execute(update(RefreshToken).where(
            RefreshToken.user_id == user_id
        ).values(is_revoked=True))
