from datetime import datetime
from uuid import UUID

from pydantic import BaseModel,Field

class FileResponse(BaseModel):
    id:UUID
    original_name:str
    mime_type:str
    size:int
    scan_status:str="PENDING_SCAN"
    index_status:str="PENDING"
    index_error:str | None=None
    folder_id:UUID | None=None
    created_at:datetime
    owner_id: UUID | None = None
    owner_username: str | None = None
    effective_role: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)


class UploadIntentCreate(BaseModel):
    filename:str=Field(min_length=1,max_length=255)
    mime_type:str=Field(min_length=1,max_length=100)
    size:int=Field(gt=0)
    content_sha256:str=Field(pattern=r"^[0-9a-fA-F]{64}$")
    folder_id:UUID | None=None


class UploadIntentResponse(BaseModel):
    id:UUID
    object_key:str
    expires_at:datetime
    multipart:bool
    chunk_size_bytes:int
    upload_url:str | None=None
    multipart_upload_id:str | None=None


class UploadPartURLsRequest(BaseModel):
    part_numbers:list[int]=Field(min_length=1,max_length=10000)


class UploadPartURL(BaseModel):
    part_number:int
    url:str


class UploadPartURLsResponse(BaseModel):
    parts:list[UploadPartURL]


class CompletedUploadPart(BaseModel):
    part_number:int=Field(ge=1,le=10000)
    etag:str=Field(min_length=1,max_length=255)


class CompleteUploadIntentRequest(BaseModel):
    parts:list[CompletedUploadPart]=Field(default_factory=list,max_length=10000)

class FileRenameRequest(BaseModel):
    name:str=Field(
        min_length=1,
        max_length=255,
    )

class FileMoveRequest(BaseModel):
    folder_id:UUID | None=None

    model_config={
        "from_attributes":True
    }
