from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.dependencies import get_current_user
from ..db.database import get_db
from ..db.models.user import User
from ..schemas.share_file import (
    ShareAccessRequest,
    ShareCreate,
    SharePublicInfo,
    ShareResponse,
)
from ..services.shared_file_service import SharedFileService


router = APIRouter(prefix="/shares", tags=["shares"])


@router.post("/share_file", response_model=ShareResponse)
def create_share_link(
    file: ShareCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    share = SharedFileService(db).create_share_link(
        share_create=file,
        user=current_user,
    )
    return {
        "id": share.id,
        "token": share.token,
        "share_url": f"{settings.FILE_SHARE_URL.rstrip('/')}/shares/{share.token}",
        "expires_at": share.expires_at,
        "is_active": share.is_active,
        "download_count": share.download_count,
    }


@router.get("/{token}", response_model=SharePublicInfo)
def get_share_info(token: str, db: Session = Depends(get_db)):
    return SharedFileService(db).get_share_info(token=token)


@router.post("/{token}/download")
def download_shared_file(
    token: str,
    request: ShareAccessRequest,
    db: Session = Depends(get_db),
):
    file, path = SharedFileService(db).get_shared_file(
        token=token,
        password=request.password,
    )
    if isinstance(path, str):
        return RedirectResponse(path)
    return FileResponse(
        path=path,
        filename=file.original_name,
        media_type=file.mime_type,
    )


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link(
    share_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    SharedFileService(db).revoke_share_link(
        share_id=share_id,
        user=current_user,
    )
