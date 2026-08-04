from datetime import datetime
from uuid import UUID

from pydantic import BaseModel,Field

class FileResponse(BaseModel):
    id:UUID
    original_name:str
    mime_type:str
    size:int
    folder_id:UUID | None=None
    created_at:datetime

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