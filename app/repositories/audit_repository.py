from .base import BaseRepository
from ..db.models.auditlog import AuditLog

from sqlalchemy.orm import Session

class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self,db:Session):
        super().__init__(db,AuditLog)

    
