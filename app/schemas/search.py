from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ContentSearchResult(BaseModel):
    id: UUID
    original_name: str
    mime_type: str
    size: int
    scan_status: str
    folder_id: UUID | None
    created_at: datetime
    score: float
    snippet: str | None = None


class ReindexResponse(BaseModel):
    status: str
    queued: int
