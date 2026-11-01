from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from ..core.enum import AuditAction, ShareExpiry
from ..core.exceptions import (
    FileNotFoundException,
    FileNotReadyException,
    InvalidShareException,
    ShareDownloadLimitExceeded,
    ShareLinkExpired,
    ShareNotFound,
)
from ..core.security import generate_share_token, hash_password, verify_password
from ..db.models.sharedFile import SharedFile
from ..db.models.user import User
from ..repositories.file_repository import FileRepository
from ..repositories.shared_file_repository import SharedFileRepository
from ..schemas.share_file import ShareCreate
from .audit_service import AuditService
from .storage_service import StorageService


class SharedFileService:
    def __init__(self, db: Session):
        self.db = db
        self.file_repository = FileRepository(db)
        self.shared_file_repository = SharedFileRepository(db)
        self.audit_service = AuditService(db)
        self.storage_service = StorageService()

    def _generate_unique_token(self) -> str:
        while True:
            token = generate_share_token()
            if not self.shared_file_repository.token_exists(token):
                return token

    def _calculate_expiry(self, *, expiry: ShareExpiry) -> datetime | None:
        days = {
            ShareExpiry.ONE_DAY: 1,
            ShareExpiry.SEVEN_DAYS: 7,
            ShareExpiry.THIRTY_DAYS: 30,
        }.get(expiry)
        if days is None:
            return None
        return datetime.now(timezone.utc) + timedelta(days=days)

    def create_share_link(self, *, user: User, share_create: ShareCreate) -> SharedFile:
        file = self.file_repository.get_by_id_and_user(
            file_id=share_create.file_id,
            user_id=user.id,
        )
        if file is None:
            raise FileNotFoundException()

        token = self._generate_unique_token()
        expires_at = self._calculate_expiry(expiry=share_create.expiry)
        password_hash = (
            hash_password(share_create.password)
            if share_create.password
            else None
        )
        share = SharedFile(
            token=token,
            file_id=share_create.file_id,
            created_by=user.id,
            expires_at=expires_at,
            password_hash=password_hash,
            max_downloads=share_create.max_downloads,
        )
        self.shared_file_repository.create(share)
        self.audit_service.log(
            user=user,
            action=AuditAction.SHARE_LINK_CREATED,
            file=file,
            details=f"Created a share link for '{file.original_name}'.",
        )
        try:
            self.db.commit()
            self.db.refresh(share)
            return share
        except Exception:
            self.db.rollback()
            raise

    def get_share_info(self, *, token: str) -> dict:
        share = self.shared_file_repository.get_by_token(token=token)
        if share is None:
            raise ShareNotFound()
        self._validate_active_share(share)

        file = self.file_repository.get_by_id(id=share.file_id)
        if file is None or file.is_deleted:
            raise ShareNotFound()

        return {
            "token": share.token,
            "original_name": file.original_name,
            "mime_type": file.mime_type,
            "size": file.size,
            "requires_password": share.password_hash is not None,
            "expires_at": share.expires_at,
            "download_count": share.download_count,
            "max_downloads": share.max_downloads,
        }

    def get_shared_file(self, *, token: str, password: str | None):
        share = self.shared_file_repository.get_by_token_for_update(token=token)
        if share is None:
            raise ShareNotFound()

        self._validate_active_share(share, persist_expiry=True)

        if share.password_hash is not None:
            if password is None or not verify_password(password, share.password_hash):
                raise InvalidShareException()

        if share.max_downloads is not None and share.download_count >= share.max_downloads:
            share.is_active = False
            self.db.commit()
            raise ShareDownloadLimitExceeded()

        file = self.file_repository.get_by_id(id=share.file_id)
        if file is None or file.is_deleted:
            raise ShareNotFound()
        if file.scan_status != "CLEAN":
            raise FileNotReadyException()

        if file.storage_backend == "r2":
            from .r2_storage_service import R2StorageService

            path = R2StorageService().create_download_url(object_key=file.storage_path)
        else:
            path = self.storage_service.get_file_path(file.storage_path)
            if not path.exists():
                raise FileNotFoundException()

        share.download_count += 1
        if share.max_downloads is not None and share.download_count >= share.max_downloads:
            # This download is allowed, but the link becomes inactive afterwards.
            share.is_active = False
        self.shared_file_repository.update(share)
        self.db.commit()
        return file, path

    def revoke_share_link(self, *, share_id: UUID, user: User) -> SharedFile:
        share = self.shared_file_repository.get_by_id_and_creator_for_update(
            share_id=share_id,
            creator_id=user.id,
        )
        if share is None:
            raise ShareNotFound()
        if not share.is_active:
            return share

        share.is_active = False
        file = self.file_repository.get_by_id(id=share.file_id)
        self.audit_service.log(
            user=user,
            action=AuditAction.REVOKE_SHARE_LINK,
            file=file,
            details=f"Revoked share link {share.id}.",
        )
        self.db.commit()
        self.db.refresh(share)
        return share

    def _validate_active_share(
        self,
        share: SharedFile,
        *,
        persist_expiry: bool = False,
    ) -> None:
        if not share.is_active:
            raise ShareLinkExpired()
        if share.expires_at is not None and share.expires_at <= datetime.now(timezone.utc):
            share.is_active = False
            if persist_expiry:
                self.shared_file_repository.update(share)
                self.db.commit()
            raise ShareLinkExpired()
