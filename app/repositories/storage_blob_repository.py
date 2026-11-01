from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db.models.file import File
from ..db.models.storage_blob import StorageBlob


class StorageBlobRepository:
    def __init__(self, db: Session):
        self.db = db

    def attach_clean_file(
        self,
        *,
        file: File,
        content_sha256: str,
    ) -> tuple[StorageBlob, str | None]:
        self.db.execute(
            insert(StorageBlob)
            .values(
                id=uuid4(),
                storage_backend=file.storage_backend,
                object_key=file.storage_path,
                content_sha256=content_sha256,
                size=file.size,
                reference_count=0,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    StorageBlob.storage_backend,
                    StorageBlob.content_sha256,
                ]
            )
        )
        statement = (
            select(StorageBlob)
            .where(
                StorageBlob.storage_backend == file.storage_backend,
                StorageBlob.content_sha256 == content_sha256,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        blob = self.db.execute(statement).scalar_one()
        duplicate_object_key = (
            file.storage_path if blob.object_key != file.storage_path else None
        )
        blob.reference_count += 1
        file.blob_id = blob.id
        file.storage_backend = blob.storage_backend
        file.storage_path = blob.object_key
        return blob, duplicate_object_key

    def release_file_reference(self, file: File) -> tuple[str, str] | None:
        if file.blob_id is None:
            return file.storage_backend, file.storage_path

        statement = (
            select(StorageBlob)
            .where(StorageBlob.id == file.blob_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        blob = self.db.execute(statement).scalar_one_or_none()
        if blob is None:
            return file.storage_backend, file.storage_path

        if blob.reference_count <= 1:
            self.db.delete(blob)
            return blob.storage_backend, blob.object_key

        blob.reference_count -= 1
        return None
