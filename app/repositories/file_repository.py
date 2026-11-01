from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models.file import File
from .base import BaseRepository


class FileRepository(BaseRepository[File]):
    def __init__(self, db: Session):
        super().__init__(db, File)

    def get_by_id_and_user(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
    ) -> File | None:
        stmt = select(File).where(
            File.id == file_id,
            File.user_id == user_id,
            File.is_deleted.is_(False),
                File.version_of.is_(None),
        )
        return cast(File | None, self.db.execute(stmt).scalar_one_or_none())

    def get_by_id_for_update(self, file_id: UUID) -> File | None:
        statement = (
            select(File)
            .where(File.id == file_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return cast(File | None, self.db.execute(statement).scalar_one_or_none())

    def get_by_folder(
        self,
        *,
        folder_id: UUID | None,
        user_id: UUID,
    ) -> list[File]:
        stmt = (
            select(File)
            .where(
                File.folder_id == folder_id,
                File.user_id == user_id,
                File.is_deleted.is_(False),
                File.version_of.is_(None),
            )
            .order_by(File.original_name)
        )
        return cast(list[File], list(self.db.execute(stmt).scalars().all()))

    def get_by_folder_any_owner(
        self,
        *,
        folder_id: UUID,
    ) -> list[File]:
        stmt = (
            select(File)
            .where(
                File.folder_id == folder_id,
                File.is_deleted.is_(False),
                File.version_of.is_(None),
            )
            .order_by(File.original_name)
        )
        return cast(list[File], list(self.db.execute(stmt).scalars().all()))

    def get_all_by_folder(
        self,
        *,
        folder_id: UUID,
    ) -> list[File]:
        stmt = select(File).where(File.folder_id == folder_id)
        return cast(list[File], list(self.db.execute(stmt).scalars().all()))

    def get_deleted_by_id_and_user(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
    ) -> File | None:
        stmt = select(File).where(
            File.id == file_id,
            File.user_id == user_id,
            File.is_deleted.is_(True),
                File.version_of.is_(None),
        )
        return cast(File | None, self.db.execute(stmt.with_for_update().execution_options(populate_existing=True)).scalar_one_or_none())

    def list_deleted_files(
        self,
        *,
        user_id: UUID,
    ) -> list[File]:
        stmt = (
            select(File)
            .where(
                File.user_id == user_id,
                File.is_deleted.is_(True),
                File.version_of.is_(None),
            )
            .order_by(File.deleted_at.desc())
        )
        return cast(list[File], list(self.db.execute(stmt).scalars().all()))

    def get_expired_deleted_files(
        self,
        *,
        user_id: UUID | None = None,
    ) -> list[File]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        conditions = [
            File.is_deleted.is_(True),
                File.version_of.is_(None),
            File.deleted_at <= cutoff,
            File.version_of.is_(None),
        ]
        if user_id is not None:
            conditions.append(File.user_id == user_id)

        stmt = select(File).where(*conditions).order_by(File.id).with_for_update(skip_locked=True)
        return cast(list[File], list(self.db.execute(stmt).scalars().all()))

    def get_by_name_and_folder(
        self,
        *,
        name: str,
        folder_id: UUID | None,
        user_id: UUID,
    ) -> File | None:
        stmt = select(File).where(
            File.original_name == name,
            File.folder_id == folder_id,
            File.user_id == user_id,
            File.is_deleted.is_(False),
                File.version_of.is_(None),
        )
        return cast(File | None, self.db.execute(stmt).scalar_one_or_none())

    def get_by_name_in_folder_any_owner(
        self,
        *,
        name: str,
        folder_id: UUID,
    ) -> File | None:
        stmt = select(File).where(
            File.original_name == name,
            File.folder_id == folder_id,
            File.is_deleted.is_(False),
                File.version_of.is_(None),
        )
        return cast(File | None, self.db.execute(stmt).scalar_one_or_none())
