from uuid import UUID

from fastapi import APIRouter,Depends,File,Form,UploadFile
from fastapi.responses import FileResponse,RedirectResponse
from sqlalchemy.orm import Session

from ..core.dependencies import get_current_user
from ..db.database import get_db
from ..db.models.user import User
from ..schemas.file import (
    CompleteUploadIntentRequest,
    FileResponse as FileSchema,
    FileRenameRequest,
    FileMoveRequest,
    UploadIntentCreate,
    UploadIntentResponse,
    UploadPartURLsRequest,
    UploadPartURLsResponse,
)
from ..services.file_service import FileService
from ..services.upload_intent_service import UploadIntentService

router=APIRouter(
    prefix="/files",
    tags=["Files"],
)

@router.post("/upload",response_model=FileSchema)
def upload_file(
    file:UploadFile=File(...),
    folder_id:UUID | None=Form(None),
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    return service.upload_file(
        upload_file=file,
        user=current_user,
        folder_id=folder_id,
    )


@router.post(
    "/upload-intents",
    response_model=UploadIntentResponse,
    status_code=201,
)
def create_upload_intent(
    data:UploadIntentCreate,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    return UploadIntentService(db).create_intent(user=current_user,data=data)


@router.post(
    "/upload-intents/{intent_id}/parts",
    response_model=UploadPartURLsResponse,
)
def create_upload_part_urls(
    intent_id:UUID,
    data:UploadPartURLsRequest,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    parts=UploadIntentService(db).create_part_urls(
        intent_id=intent_id,
        user=current_user,
        part_numbers=data.part_numbers,
    )
    return {"parts":parts}


@router.post(
    "/upload-intents/{intent_id}/complete",
    response_model=FileSchema,
)
def complete_upload_intent(
    intent_id:UUID,
    data:CompleteUploadIntentRequest,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    parts=[
        {"PartNumber":part.part_number,"ETag":part.etag}
        for part in data.parts
    ]
    return UploadIntentService(db).complete_intent(
        intent_id=intent_id,
        user=current_user,
        parts=parts,
    )


@router.delete("/upload-intents/{intent_id}",status_code=204)
def cancel_upload_intent(
    intent_id:UUID,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    UploadIntentService(db).cancel_intent(intent_id=intent_id,user=current_user)

@router.get("/{file_id}/download")
def download_file(
    file_id:UUID,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    file,path=service.download_file(
        file_id=file_id,
        user=current_user,
    )

    if isinstance(path,str):
        return RedirectResponse(path)

    return FileResponse(
        path=path,
        filename=file.original_name,
        media_type=file.mime_type,
    )

@router.patch("/{file_id}/rename",response_model=FileSchema)
def rename_file(
    file_id:UUID,
    data:FileRenameRequest,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    return service.rename_file(
        file_id=file_id,
        data=data,
        user=current_user,
    )

@router.patch("/{file_id}/move",response_model=FileSchema)
def move_file(
    file_id:UUID,
    data:FileMoveRequest,
    user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    return service.move_file(
        file_id=file_id,
        data=data,
        user=user,
    )

@router.delete("/{file_id}")
def delete_file(
    file_id:UUID,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    service.delete_file(
        file_id=file_id,
        user=current_user,
    )

    return{
        "message":"File Deleted Successfully"
    }

@router.post("/{file_id}/restore")
def restore_file(
    file_id:UUID,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    return service.restore_file(
        file_id=file_id,
        user=current_user,
    )

@router.delete("/{file_id}/permanent_delete")
def permanently_delete_file(
    file_id:UUID,
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    service.permanently_delete_file(
        file_id=file_id,
        user=current_user,
    )

    return {
        "message":"File Deleted Permanently."
    }

@router.get("/recycle-bin")
def get_recycle_bin(
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    return service.get_recycle_bin(
        user=current_user,
    )

@router.post("/cleanup")
def cleanup(
    current_user:User=Depends(get_current_user),
    db:Session=Depends(get_db),
):
    service=FileService(db)

    deleted=service.cleanup_expired_files(user=current_user)

    return {
        "deleted_files":deleted,
    }

