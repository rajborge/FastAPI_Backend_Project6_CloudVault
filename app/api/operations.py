from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models.file import File
from app.db.models.user import User

router = APIRouter(tags=["Operations"])


@router.get("/users/me/storage")
def storage_summary(current: User = Depends(get_current_user)):
    return {
        "used": current.storage_used,
        "reserved": current.storage_reserved,
        "limit": current.storage_limit,
        "is_verified": current.is_verified,
        "mfa_enabled": bool(current.mfa_secret),
    }


@router.get("/users/me/jobs")
def job_summary(current: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.execute(
        select(File.scan_status, File.index_status, func.count())
        .where(
            File.user_id == current.id,
            File.is_deleted.is_(False),
            File.version_of.is_(None),
        )
        .group_by(File.scan_status, File.index_status)
    ).all()
    return [
        {"scan": scan, "index": index, "count": count} for scan, index, count in rows
    ]
