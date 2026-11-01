from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ..core.enum import ShareExpiry


class ShareCreate(BaseModel):
    file_id: UUID
    expiry: ShareExpiry = ShareExpiry.NEVER
    password: str | None = Field(default=None, max_length=128)
    max_downloads: int | None = Field(default=None, ge=1)


class ShareResponse(BaseModel):
    id: UUID
    token: str
    share_url: str
    expires_at: datetime | None
    is_active: bool
    download_count: int


class ShareAccessRequest(BaseModel):
    password: str | None = None
    resolve: bool = False


# Backward-compatible alias for your existing imports/tests.
shareAccessRequest = ShareAccessRequest


class SharePublicInfo(BaseModel):
    token: str
    original_name: str
    mime_type: str
    size: int
    requires_password: bool
    expires_at: datetime | None
    download_count: int
    max_downloads: int | None
