from uuid import UUID
from datetime import datetime,timedelta,timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models.file import File
from .base import BaseRepository

class FileRepository(BaseRepository[File]):
    def __init__(self,db:Session):
        super().__init__(db,File)

    def get_by_id_and_user(
            self,
            *,
            file_id:UUID,
            user_id:UUID,
    )->File | None:
        stmt=(
            select(File)
            .where(
                File.id==file_id,
                File.user_id==user_id,
                File.is_deleted==False,
            )
        )

        result=self.db.execute(stmt)

        return cast(File | None,result.scalar_one_or_none())
    
    def get_by_folder(
            self,
            *,
            folder_id:UUID | None,
            user_id:UUID,
    )->list[File]:
        stmt=(
            select(File)
            .where(
                File.folder_id==folder_id,
                File.user_id==user_id,
                File.is_deleted==False,
            )
            .order_by(File.original_name)
        )

        result=self.db.execute(stmt)

        return cast(list[File],(result.scalars().all()))
    
    def get_deleted_by_id_and_user(
            self,
            *,
            file_id:UUID,
            user_id:UUID,
    )->File | None:
        stmt=(
            select(File)
            .where(
                File.id==file_id,
                File.user_id==user_id,
                File.is_deleted==True,
            )
        )

        result=self.db.execute(stmt)

        return cast(File | None,result.scalar_one_or_none())
    
    def list_deleted_files(
            self,
            *,
            user_id:UUID,
    )->list[File]:
        stmt=(
            select(File)
            .where(
                File.user_id==user_id,
                File.is_deleted==True,
            )
            .order_by(File.deleted_at.desc())
        )

        result=self.db.execute(stmt)

        return cast(list[File],(result.scalars().all()))
    
    def get_expired_deleted_files(
            self,
    )->list[File]:
        
        cutoff=datetime.now(timezone.utc) - timedelta(days=30)

        stmt=(
            select(File)
            .where(
                File.is_deleted==True,
                File.deleted_at<=cutoff,
            )
        )

        result=self.db.execute(stmt)

        return cast(list[File],(result.scalars().all()))
    
    def get_by_name_and_folder(
         self,
         *,
         name: str,
         folder_id: UUID | None,
         user_id: UUID,
    ) -> File | None:

        stmt = (
            select(File)
            .where(
                File.original_name == name,
                File.folder_id == folder_id,
                File.user_id == user_id,
                File.is_deleted == False,
            )
        )

        result = self.db.execute(stmt)

        return cast(File | None, result.scalar_one_or_none())
