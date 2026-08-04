from fastapi import status,HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime,timezone

from ..repositories.shared_file_repository import SharedFileRepository
from ..repositories.file_repository import FileRepository
from .audit_service import AuditService
from .storage_service import StorageService

from ..db.models.user import User
from ..db.models.sharedFile import SharedFile
from ..core.enum import AuditAction,ShareExpiry

from ..schemas.share_file import ShareCreate

from ..core.security import generate_share_token,hash_password,verify_password
from ..core.exceptions import ShareNotFound,ShareLinkExpired,InvalidShareException

class SharedFileService:
    def __init__(self,db:Session):
        self.db=db

        self.file_repository=FileRepository(db)
        self.shared_file_repository=SharedFileRepository(db)

        self.audit_service=AuditService(db)
        self.storage_service=StorageService()

    def _generate_unique_token(
        self,
    )->str:
        while True:
            token=generate_share_token()

            if not self.shared_file_repository.token_exists(token):
                return token
            
    def _calculate_expiry(
            self,
            *,
            expiry:ShareExpiry,
    )->datetime | None:
        now=datetime.now(timezone.utc)
            
    def create_share_link(
            self,
            *,
            user:User,
            share_create:ShareCreate,
    ):
        file=self.file_repository.get_by_id_and_user(
            file_id=share_create.file_id,
            user_id=user.id,
        )

        if file is None:
            FileNotFoundError()

        token=self._generate_unique_token()

        expires_at=self._calculate_expiry(
            expiry=share_create.expiry,
        )

        password_hash=None

        if share_create.password is not None:
            password_hash=hash_password(share_create.password)

        share=SharedFile(
            token=token,
            file_id=share_create.file_id,
            created_by=user.id,
            expires_at=expires_at,
            password_hash=password_hash,
        )

        self.shared_file_repository.create(share)

        self.audit_service.log(
            user=user,
            action=AuditAction.SHARE_LINK_CREATED,
            file=file,
            details=f"Created the Share Link for {file.original_name}."
        )

        try:
            self.db.commit()
            self.db.refresh(share)
            return share
        except:
            self.db.rollback()
            raise

    def get_shared_file(
        self,
        *,
        token:str,
        password:str | None,
    ):
        share=self.shared_file_repository.get_by_token(token=token)
        print("share File Id:",share.file_id)

        if share is None:
            raise ShareNotFound()
        print("Share:",share)

        if not share.is_active:
            raise HTTPException(status_code=status.HTTP_410_GONE,detail="Share Link is Not Active.")
        
        if (
            share.expires_at is not None
            and share.expires_at<=datetime.now(timezone.utc)
        ):
            share.is_active=False

            self.shared_file_repository.update(share)

            self.db.commit()

            raise ShareLinkExpired()
        
        if share.password_hash is not None:
           if password is None:
               raise InvalidShareException()
           if not verify_password(password,share.password_hash):
               raise InvalidShareException()  
        
        file=self.file_repository.get_by_id(
            id=share.file_id,
        )

        if file is None:
            raise Exception("File Object is Gone")
        print("File:",file)
        
        path=self.storage_service.get_file_path(
            file.storage_path,
        ) 
        
        print("Storage_path:",file.storage_path)
        print("Resolved path:",path)
        print("Exists:",path.exists())

        if not path.exists():
            raise Exception(f"FILE DOES NOT EXIST ON DISK: {path}")
        
        share.download_count+=1

        self.shared_file_repository.update(share)

        self.db.commit()

        return file,path
    