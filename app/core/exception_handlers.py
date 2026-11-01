from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse

from ..core.exceptions import(
    EmailAlreadyExistsException,
    UsernameAlreadyExistsException,
    UserNotFoundException,
    InactiveUserException,
    InvalidCredentialsException,
    FolderAlreadyExists,
    FolderNotFound,
    StorageQuotaExceededException,
    ShareNotFound,
    ShareLinkExpired,
    ShareDownloadLimitExceeded,
    InvalidShareException,
    DuplicateFileNameException,
    FileNotFoundException,
    InvalidFolderMoveException,
    FileNotReadyException,
    UploadIntentNotFoundException,
    UploadIntentExpiredException,
    InvalidUploadException,
    ObjectStorageConfigurationException,
    PermissionNotFoundException,
)

def register_exception_handlers(app:FastAPI):
    @app.exception_handler(EmailAlreadyExistsException)
    async def email_exists_handler(
            request:Request,
            exc:EmailAlreadyExistsException,
    ):
        return JSONResponse(
            status_code=409,
            content={"detail":"Email already registered."}
        )
    
    @app.exception_handler(UsernameAlreadyExistsException)
    async def username_exists_handler(
        request: Request,
        exc: UsernameAlreadyExistsException,
    ):
        return JSONResponse(
            status_code=409,
            content={"detail": "Username already exists."},
        )

    @app.exception_handler(InvalidCredentialsException)
    async def invalid_credentials_handler(
        request: Request,
        exc: InvalidCredentialsException,
    ):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid credentials."},
        )

    @app.exception_handler(UserNotFoundException)
    async def user_not_found_handler(
        request: Request,
        exc: UserNotFoundException,
    ):
        return JSONResponse(
            status_code=404,
            content={"detail": "User not found."},
        )

    @app.exception_handler(InactiveUserException)
    async def inactive_user_handler(
        request: Request,
        exc: InactiveUserException,
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "User account is inactive."},
        )
    
    @app.exception_handler(FolderAlreadyExists)
    async def folder_already_exists_handler(
        request:Request,
        exc:FolderAlreadyExists,
    ):
        return JSONResponse(
            status_code=409,
            content={"detail":"Folder already exists"}
        )
    
    @app.exception_handler(FolderNotFound)
    async def folder_not_found_handler(
        request:Request,
        exc:FolderNotFound
    ):
        return JSONResponse(
            status_code=404,
            content={"detail":"Folder Not Found"}
        )
    
    @app.exception_handler(StorageQuotaExceededException)
    async def storage_quota_exceeded_handler(
        request:Request,
        exc:StorageQuotaExceededException
    ):
        return JSONResponse(
            status_code=413,
            content={"detail":"Storage Limit Exceeded."}
        )
    
    @app.exception_handler(ShareNotFound)
    async def share_not_found_handler(
        request:Request,
        exc:ShareNotFound
    ):
        return JSONResponse(
            status_code=404,
            content={"detail":"Share Not Found"}
        )
    
    @app.exception_handler(ShareLinkExpired)
    async def share_link_expired_handler(
        request:Request,
        exc:ShareLinkExpired
    ):
        return JSONResponse(
            status_code=410,
            content={"detail":"Share Link Has Expired."}
        )

    @app.exception_handler(ShareDownloadLimitExceeded)
    async def share_download_limit_handler(
        request:Request,
        exc:ShareDownloadLimitExceeded,
    ):
        return JSONResponse(
            status_code=410,
            content={"detail":"Share download limit has been reached."},
        )
    
    @app.exception_handler(InvalidShareException)
    async def invalid_share_exception(
        request:Request,
        exc:InvalidShareException,
    ):
        return JSONResponse(
            status_code=401,
            content={"detail":"Invalid Share Password."}
        )
    
    @app.exception_handler(DuplicateFileNameException)
    async def duplicate_file_name_handler(
        request:Request,
        exc:DuplicateFileNameException,
    ):
        return JSONResponse(
            status_code=409,
            content={"detail":"A File with this Name Already Exists."}
        )
    
    @app.exception_handler(FileNotFoundException)
    async def file_not_found_exception(
        request:Request,
        exc:FileNotFoundException,
    ):
        return JSONResponse(
            status_code=404,
            content={"detail":"File not found."}
        )
    
    @app.exception_handler(InvalidFolderMoveException)
    async def invalid_folder_move_exception(
        request:Request,
        exc:InvalidFolderMoveException,
    ):
        return JSONResponse(
            status_code=400,
            content={"detail":"Invalid Folder destination."}
        )

    @app.exception_handler(FileNotReadyException)
    async def file_not_ready_handler(request:Request,exc:FileNotReadyException):
        return JSONResponse(
            status_code=409,
            content={"detail":"File is not available until scanning completes."},
        )

    @app.exception_handler(UploadIntentNotFoundException)
    async def upload_intent_not_found_handler(
        request:Request,
        exc:UploadIntentNotFoundException,
    ):
        return JSONResponse(status_code=404,content={"detail":"Upload intent not found."})

    @app.exception_handler(UploadIntentExpiredException)
    async def upload_intent_expired_handler(
        request:Request,
        exc:UploadIntentExpiredException,
    ):
        return JSONResponse(status_code=410,content={"detail":"Upload intent expired."})

    @app.exception_handler(InvalidUploadException)
    async def invalid_upload_handler(request:Request,exc:InvalidUploadException):
        return JSONResponse(status_code=422,content={"detail":"Uploaded object failed validation."})

    @app.exception_handler(ObjectStorageConfigurationException)
    async def object_storage_unavailable_handler(
        request:Request,
        exc:ObjectStorageConfigurationException,
    ):
        return JSONResponse(status_code=503,content={"detail":"Object storage is not configured."})

    @app.exception_handler(PermissionNotFoundException)
    async def permission_not_found_handler(
        request:Request,
        exc:PermissionNotFoundException,
    ):
        return JSONResponse(status_code=404,content={"detail":"Permission not found."})
