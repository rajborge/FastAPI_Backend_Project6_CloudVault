from pydantic import BaseModel
from uuid import UUID

from datetime import datetime

from ..db.models.enum import ShareExpiry

class ShareCreate(BaseModel):
    file_id:UUID
    expiry:ShareExpiry=ShareExpiry.NEVER
    password:str | None=None

class ShareResponse(BaseModel):
    id:UUID
    token:str
    share_url:str
    expires_at:datetime | None
    is_active:bool
    download_count:int

class shareAccessRequest(BaseModel):
    password:str  | None=None