from sqlalchemy.orm import Session

from ..repositories.audit_repository import AuditRepository
from ..db.models.user import User
from ..db.models.file import File
from ..db.models.folder import Folder
from ..db.models.auditlog import AuditLog
from ..core.enum import AuditAction

class AuditService:
    def __init__(self,db:Session):
        self.db=db
        self.audit_repository=AuditRepository(db)

    def log(
        self,
        *,
        user:User,
        action:AuditAction,
        details:str,
        file:File | None=None,
        folder:Folder | None=None,
    ):
        audit=AuditLog(
            user_id=user.id,
            action=action.value,
            details=details,
            file_id=file.id if file else None,
            folder_id=folder.id if folder else None,
        )

        self.audit_repository.create(audit)
