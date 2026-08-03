from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models.folder import Folder
from .base import BaseRepository

class FolderRepository(BaseRepository[Folder]):
    def __init__(self,db:Session):
        super().__init__(db,Folder)

    def folder_exists(
            self,
            *,
            user_id:UUID,
            parent_id:UUID | None,
            name:str,
    )->bool:
        stmt=(
            select(Folder).where(
            Folder.user_id==user_id,
            Folder.parent_id==parent_id,
            Folder.name==name,
            )
        )

        result=self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
        
    def get_children(
            self,
            user_id:UUID,
            parent_id:UUID | None,
    )->list[Folder]:
            stmt=(
                select(Folder)
                .where(
                Folder.parent_id==parent_id,
                Folder.user_id==user_id,
            )
            .order_by(Folder.name)
            )
            
            result=self.db.execute(stmt)
            return list(result.scalars().all())
    
    def get_by_id_and_user(
            self,
            folder_id:UUID,
            user_id:UUID,
    )->Folder | None:
         stmt=(
              select(Folder)
              .where(
                   Folder.id==folder_id,
                   Folder.user_id==user_id,
              )
         )
         result=self.db.execute(stmt)
         return result.scalar_one_or_none()
    
    def folder_exists_except(
            self,
            *,
            folder_id:UUID,
            user_id:UUID,
            parent_id:UUID | None,
            name:str,
    )->bool:
         stmt=(
            select(Folder)
            .where(
                 Folder.user_id==user_id,
                 Folder.parent_id==parent_id,
                 Folder.name==name,
                 Folder.id!=folder_id
            )
         )
         result=self.db.execute(stmt)
         return result.scalar_one_or_none() is not None
    
    def get_by_parent(
        self,
        *,
        parent_id:UUID| None,
        user_id:UUID,
    ):
        stmt=(
            select(Folder)
            .where(
                Folder.parent_id==parent_id,
                Folder.user_id==user_id,
            )
            .order_by(Folder.name)
        )

        result=self.db.execute(stmt)
        
        return list(result.scalars().all())

