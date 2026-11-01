from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ..core.enum import PermissionRole, ResourceType


class PermissionGrantRequest(BaseModel):
    # Backward-compatible: old clients may still send target_user_id.
    target_user_id: UUID | None = None
    # New UI can use username, email, or UUID text.
    target_identifier: str | None = Field(default=None, min_length=1, max_length=255)
    resource_type: ResourceType
    resource_id: UUID
    role: PermissionRole


class PermissionResponse(BaseModel):
    id: UUID
    user_id: UUID
    resource_type: ResourceType
    resource_id: UUID
    role: PermissionRole
    created_at: datetime
    username: str | None = None
    email: str | None = None

    model_config = {"from_attributes": True}


class SharedResourceResponse(BaseModel):
    permission_id: UUID
    resource_type: ResourceType
    resource_id: UUID
    role: PermissionRole
    name: str
    owner_id: UUID
    created_at: datetime
    mime_type: str | None = None
    size: int | None = None
    scan_status: str | None = None
    parent_id: UUID | None = None
    shared_at: datetime
    owner_username: str
    owner_email: str | None = None
    recipient_id: UUID
    recipient_username: str
    recipient_email: str | None = None
    effective_role: PermissionRole
    capabilities: dict[str, bool]
