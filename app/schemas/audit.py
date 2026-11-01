from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: UUID
    action: str
    details: str
    file_id: UUID | None
    folder_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
