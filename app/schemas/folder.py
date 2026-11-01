from uuid import UUID
from pydantic import BaseModel,Field
from datetime import datetime

from .file import FileResponse

class FolderCreate(BaseModel):
    name:str=Field(min_length=1,max_length=255)
    parent_id:UUID | None=None

class FolderResponse(BaseModel):
    id:UUID
    name:str
    parent_id:UUID | None=None
    created_at:datetime
    owner_id: UUID | None = None
    owner_username: str | None = None
    effective_role: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)

class FolderUpdate(BaseModel):
    name:str=Field(min_length=1,max_length=255)

class FolderContentsResponse(BaseModel):
    folders:list[FolderResponse]
    files:list[FileResponse]

class FolderMoveRequest(BaseModel):
    parent_id:UUID | None=None

    model_config={
        "from_attributes":True
    }
