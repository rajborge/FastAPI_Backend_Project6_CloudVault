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
    parent_id:UUID | None
    created_at:datetime

class FolderUpdate(BaseModel):
    name:str=Field(min_length=1,max_length=255)

class FolderContentsResponse(BaseModel):
    folders:list[FolderResponse]
    files:list[FileResponse]

    model_config={
        "from_attributes":True
    }
