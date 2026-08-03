from fastapi import APIRouter,Depends
from fastapi.responses import FileResponse
from datetime import datetime,timezone,timedelta

from sqlalchemy.orm import Session

from ..schemas.share_file import ShareCreate,ShareResponse,shareAccessRequest

from ..services.shared_file_service import SharedFileService

from ..db.database import get_db
from ..core.dependencies import get_current_user

from ..db.models.user import User
from ..db.models.sharedFile import SharedFile

from ..core.config import settings

router=APIRouter(
    prefix="/shares",
    tags=["shares"],
)

@router.post(
    "/share_file",
    response_model=ShareResponse
)
def create_share_link(
    file:ShareCreate,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=SharedFileService(db)

    share=service.create_share_link(
        share_create=file,
        user=current_user,
    )

    share_url=(
        f"{settings.FILE_SHARE_URL}/shares/{share.token}"
    )


    return {
        "id":share.id,
        "token":share.token,
        "share_url":share_url,
        "expires_at":share.expires_at,
        "is_active":share.is_active,
        "download_count":share.download_count,
    }

@router.post(
    "/{token}/download"
)
def download_shared_file(
    token:str,
    request:shareAccessRequest,
    db:Session=Depends(get_db),
):
    service=SharedFileService(db)

    file,path=service.get_shared_file(
        token=token,
        password=request.password,
    )

    return FileResponse(
        path=path,
        filename=file.original_name,
        media_type=file.mime_type,
    )

