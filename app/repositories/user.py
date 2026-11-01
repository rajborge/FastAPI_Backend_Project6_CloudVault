from sqlalchemy import select,or_,update,func
from sqlalchemy.orm import Session
from uuid import UUID

from ..db.models.user import User
from .base import BaseRepository

class UserRepository(BaseRepository[User]):
    def __init__(self,db:Session):
        super().__init__(db,User)

    def get_user_by_email(self,email:str)->User | None:
        stmt=select(User).where(User.email==email)
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()

    def release_storage(self, user_id: UUID, size: int) -> None:
        # The database performs arithmetic under its row lock; never write an
        # absolute counter copied from a previously loaded User instance.
        self.db.execute(update(User).where(User.id == user_id).values(
            storage_used=func.greatest(0, User.storage_used - size)
        ).execution_options(synchronize_session=False))

    def invalidate_access(self, user_id: UUID) -> None:
        self.db.execute(update(User).where(User.id == user_id).values(
            auth_version=User.auth_version + 1
        ).execution_options(synchronize_session=False))
    
    def get_user_by_username(self,username:str)->User |None:
        stmt=select(User).where(User.username==username)
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_by_provider_user_id(self,provider_user_id:str)->User | None:
        stmt=select(User).where(User.provider_user_id==provider_user_id)
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_by_identifier(self,identifier:str)->User | None:
        stmt=(
            select(User)
            .where(
                or_(
                    User.email==identifier,
                    User.username==identifier,
                )
            )
        )
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()

    def get_by_id_for_update(self,user_id:UUID)->User | None:
        stmt=(
            select(User)
            .where(User.id==user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()
