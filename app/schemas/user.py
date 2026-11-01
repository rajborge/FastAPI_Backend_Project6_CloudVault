from pydantic import BaseModel,EmailStr,ConfigDict
from uuid import UUID

class UserResponse(BaseModel):
    id: UUID
    storage_used: int
    storage_reserved: int
    storage_limit: int
    is_verified: bool
    username:str
    email:EmailStr

    model_config=ConfigDict(
        from_attributes=True
    )
