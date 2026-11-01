from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.enum import AuditAction
from ..core.exceptions import (
    FolderNotFound,
    InvalidUploadException,
    StorageQuotaExceededException,
    UploadIntentExpiredException,
    UploadIntentNotFoundException,
    UserNotFoundException,
)
from ..db.models.file import File
from ..db.models.upload_intent import UploadIntent
from ..db.models.user import User
from ..repositories.file_repository import FileRepository
from ..repositories.folder_repository import FolderRepository
from ..repositories.upload_intent_repository import UploadIntentRepository
from ..repositories.user import UserRepository
from ..schemas.file import UploadIntentCreate
from .audit_service import AuditService
from .r2_storage_service import R2StorageService
from ..tasks.file_task import enqueue_file_scan


class UploadIntentService:
    def __init__(self, db: Session, storage: R2StorageService | None = None):
        self.db = db
        self.storage = storage or R2StorageService()
        self.user_repository = UserRepository(db)
        self.intent_repository = UploadIntentRepository(db)
        self.file_repository = FileRepository(db)
        self.folder_repository = FolderRepository(db)
        self.audit_service = AuditService(db)
        self.chunk_size_bytes = settings.R2_MULTIPART_PART_SIZE_MB * 1024 * 1024
        self.multipart_threshold_bytes = (
            settings.R2_UPLOAD_MULTIPART_THRESHOLD_MB * 1024 * 1024
        )

    def create_intent(self, *, user: User, data: UploadIntentCreate) -> dict:
        maximum_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if data.size > maximum_size:
            raise StorageQuotaExceededException()

        if data.folder_id is not None:
            folder = self.folder_repository.get_by_id_and_user(
                folder_id=data.folder_id,
                user_id=user.id,
            )
            if folder is None:
                raise FolderNotFound()

        locked_user = self.user_repository.get_by_id_for_update(user.id)
        if locked_user is None:
            raise UserNotFoundException()

        reserved_bytes = locked_user.storage_reserved or 0
        if locked_user.storage_used + reserved_bytes + data.size > locked_user.storage_limit:
            raise StorageQuotaExceededException()

        intent_id = uuid4()
        object_key = f"users/{locked_user.id}/objects/{intent_id}"
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.UPLOAD_INTENT_TTL_MINUTES
        )
        multipart = data.size >= self.multipart_threshold_bytes
        multipart_upload_id = None
        upload_url = None
        content_sha256 = data.content_sha256.lower()

        try:
            if multipart:
                multipart_upload_id = self.storage.create_multipart_upload(
                    object_key=object_key,
                    content_type=data.mime_type,
                    content_sha256=content_sha256,
                )
            else:
                upload_url = self.storage.create_upload_url(
                    object_key=object_key,
                    content_type=data.mime_type,
                    content_sha256=content_sha256,
                    content_length=data.size,
                )

            intent = UploadIntent(
                id=intent_id,
                user_id=locked_user.id,
                folder_id=data.folder_id,
                object_key=object_key,
                original_name=data.filename,
                mime_type=data.mime_type,
                expected_size=data.size,
                content_sha256=content_sha256,
                multipart_upload_id=multipart_upload_id,
                status="OPEN",
                expires_at=expires_at,
            )
            locked_user.storage_reserved = reserved_bytes + data.size
            self.intent_repository.create(intent)
            self.db.commit()
            self.db.refresh(intent)
        except Exception:
            self.db.rollback()
            if multipart_upload_id is not None:
                try:
                    self.storage.abort_multipart_upload(
                        object_key=object_key,
                        upload_id=multipart_upload_id,
                    )
                except Exception:
                    pass
            raise

        return {
            "id": intent.id,
            "object_key": object_key,
            "expires_at": expires_at,
            "multipart": multipart,
            "chunk_size_bytes": self.chunk_size_bytes,
            "upload_url": upload_url,
            "multipart_upload_id": multipart_upload_id,
        }

    def create_part_urls(
        self,
        *,
        intent_id: UUID,
        user: User,
        part_numbers: list[int],
    ) -> list[dict]:
        intent = self._get_open_intent(intent_id=intent_id, user=user)
        if intent.multipart_upload_id is None:
            raise InvalidUploadException()

        if len(set(part_numbers)) != len(part_numbers):
            raise InvalidUploadException()

        maximum_parts = ceil(intent.expected_size / self.chunk_size_bytes)
        if any(number < 1 or number > maximum_parts for number in part_numbers):
            raise InvalidUploadException()

        return [
            {
                "part_number": number,
                "url": self.storage.create_part_upload_url(
                    object_key=intent.object_key,
                    upload_id=intent.multipart_upload_id,
                    part_number=number,
                    content_length=min(
                        self.chunk_size_bytes,
                        intent.expected_size - (number - 1) * self.chunk_size_bytes,
                    ),
                ),
            }
            for number in sorted(part_numbers)
        ]

    def complete_intent(
        self,
        *,
        intent_id: UUID,
        user: User,
        parts: list[dict],
    ) -> File:
        intent = self.intent_repository.get_for_user_for_update(intent_id=intent_id, user_id=user.id)
        if intent is None:
            raise UploadIntentNotFoundException()
        if intent.status == "COMPLETED" and intent.file_id is not None:
            file = self.file_repository.get_by_id(id=intent.file_id)
            if file is not None and not file.is_deleted:
                return file
            raise InvalidUploadException()
        intent = self._get_open_intent(intent_id=intent_id, user=user, lock=True)
        locked_user = self.user_repository.get_by_id_for_update(user.id)
        if locked_user is None:
            raise UserNotFoundException()

        if intent.multipart_upload_id is None:
            if parts:
                raise InvalidUploadException()
            object_metadata = self.storage.head_object_if_exists(
                object_key=intent.object_key
            )
            if object_metadata is None:
                raise InvalidUploadException()
        else:
            object_metadata = self.storage.head_object_if_exists(object_key=intent.object_key)
            if object_metadata is None:
                expected_part_count = ceil(intent.expected_size / self.chunk_size_bytes)
                part_numbers = sorted(part["PartNumber"] for part in parts)
                if part_numbers != list(range(1, expected_part_count + 1)):
                    raise InvalidUploadException()
                object_metadata = self.storage.complete_multipart_upload(
                    object_key=intent.object_key,
                    upload_id=intent.multipart_upload_id,
                    parts=parts,
                )

        if (
            object_metadata["size"] != intent.expected_size
            or object_metadata["content_type"] != intent.mime_type
            or object_metadata["content_sha256"] != intent.content_sha256
        ):
            self.storage.delete_object(object_key=intent.object_key)
            self._release_reservation(locked_user, intent.expected_size)
            intent.status = "FAILED"
            self.db.commit()
            raise InvalidUploadException()

        folder = None
        if intent.folder_id is not None:
            folder = self.folder_repository.get_by_id_and_user(
                folder_id=intent.folder_id,
                user_id=locked_user.id,
            )
            if folder is None:
                raise FolderNotFound()

        file = File(
            original_name=intent.original_name,
            stored_name=intent.object_key.rsplit("/", 1)[-1],
            mime_type=intent.mime_type,
            size=intent.expected_size,
            storage_path=intent.object_key,
            content_sha256=intent.content_sha256,
            storage_backend="r2",
            scan_status="PENDING_SCAN",
            user_id=locked_user.id,
            folder_id=intent.folder_id,
        )
        self.file_repository.create(file)
        self.db.flush()
        intent.file_id = file.id
        self._release_reservation(locked_user, intent.expected_size)
        locked_user.storage_used += intent.expected_size
        intent.status = "COMPLETED"
        self.audit_service.log(
            user=locked_user,
            action=AuditAction.UPLOAD_FILE,
            file=file,
            folder=folder,
            details=f"Uploaded '{file.original_name}' to object storage",
        )
        self.db.commit()
        self.db.refresh(file)
        enqueue_file_scan(file.id)
        return file

    def cancel_intent(self, *, intent_id: UUID, user: User) -> None:
        intent = self.intent_repository.get_for_user_for_update(
            intent_id=intent_id,
            user_id=user.id,
        )
        if intent is None:
            raise UploadIntentNotFoundException()
        if intent.status != "OPEN":
            raise InvalidUploadException()

        locked_user = self.user_repository.get_by_id_for_update(user.id)
        if locked_user is None:
            raise UserNotFoundException()

        if intent.multipart_upload_id is not None:
            self.storage.abort_multipart_upload(
                object_key=intent.object_key,
                upload_id=intent.multipart_upload_id,
            )
        else:
            self.storage.delete_object(object_key=intent.object_key)

        self._release_reservation(locked_user, intent.expected_size)
        intent.status = "CANCELLED"
        self.db.commit()

    def resume_intent(self, *, intent_id: UUID, user: User) -> dict:
        intent = self.intent_repository.get_for_user_for_update(intent_id=intent_id, user_id=user.id)
        if intent is None:
            raise UploadIntentNotFoundException()
        if intent.status == "COMPLETED" and intent.file_id:
            file = self.file_repository.get_by_id(id=intent.file_id)
            if file is not None and not file.is_deleted:
                from app.schemas.file import FileResponse
                return {"completed_file": FileResponse.model_validate(file, from_attributes=True).model_dump(mode="json")}
        intent = self._get_open_intent(intent_id=intent_id, user=user)
        multipart = intent.multipart_upload_id is not None
        uploaded = self.storage.head_object_if_exists(object_key=intent.object_key) is not None
        return {
            "id": intent.id, "object_key": intent.object_key, "expires_at": intent.expires_at,
            "multipart": multipart, "chunk_size_bytes": self.chunk_size_bytes,
            "multipart_upload_id": intent.multipart_upload_id,
            "upload_url": None if multipart else self.storage.create_upload_url(
                object_key=intent.object_key, content_type=intent.mime_type,
                content_sha256=intent.content_sha256, content_length=intent.expected_size),
            "completed_parts": self.storage.list_uploaded_parts(object_key=intent.object_key,
                upload_id=intent.multipart_upload_id) if multipart and not uploaded else [],
            "already_uploaded": uploaded,
        }

    def cleanup_expired_intents(self) -> int:
        now = datetime.now(timezone.utc)
        expired_intents = self.intent_repository.list_expired_open(now=now)
        cleaned_count = 0

        for expired in expired_intents:
            intent = self.intent_repository.get_for_user_for_update(
                intent_id=expired.id,
                user_id=expired.user_id,
            )
            if intent is None or intent.status != "OPEN" or intent.expires_at > now:
                continue

            locked_user = self.user_repository.get_by_id_for_update(intent.user_id)
            if locked_user is None:
                self.db.rollback()
                continue

            try:
                if intent.multipart_upload_id is not None:
                    object_metadata = self.storage.head_object_if_exists(
                        object_key=intent.object_key
                    )
                    if object_metadata is not None:
                        self.storage.delete_object(object_key=intent.object_key)
                    else:
                        self.storage.abort_multipart_upload(
                            object_key=intent.object_key,
                            upload_id=intent.multipart_upload_id,
                        )
                else:
                    self.storage.delete_object(object_key=intent.object_key)

                self._release_reservation(locked_user, intent.expected_size)
                intent.status = "EXPIRED"
                self.db.commit()
                cleaned_count += 1
            except Exception:
                self.db.rollback()

        return cleaned_count

    def _get_open_intent(
        self,
        *,
        intent_id: UUID,
        user: User,
        lock: bool = False,
    ) -> UploadIntent:
        if lock:
            intent = self.intent_repository.get_for_user_for_update(
                intent_id=intent_id,
                user_id=user.id,
            )
        else:
            intent = self.intent_repository.get_for_user_for_update(
                intent_id=intent_id,
                user_id=user.id,
            )
        if intent is None:
            raise UploadIntentNotFoundException()
        if intent.expires_at <= datetime.now(timezone.utc):
            raise UploadIntentExpiredException()
        if intent.status != "OPEN":
            raise InvalidUploadException()
        return intent

    @staticmethod
    def _release_reservation(user: User, size: int) -> None:
        user.storage_reserved = max(0, user.storage_reserved - size)
