from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.dependencies import get_current_user
from ..db.database import get_db
from ..db.models.user import User
from ..repositories.audit_repository import AuditRepository
from ..schemas.audit import AuditLogResponse


router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return AuditRepository(db).list_for_user(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
