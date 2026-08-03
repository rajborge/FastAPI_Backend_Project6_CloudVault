from sqlalchemy import select,or_
from sqlalchemy.orm import Session

from ..db.models.user import User
from .base import BaseRepository

class UserRepository(BaseRepository[User]):
    def __init__(self,db:Session):
        super().__init__(db,User)

    def get_user_by_email(self,email:str)->User | None:
        stmt=select(User).where(User.email==email)
        result=self.db.execute(stmt)
        return result.scalar_one_or_none()
    
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