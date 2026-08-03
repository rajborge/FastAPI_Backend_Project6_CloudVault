from pydantic import BaseModel,EmailStr,ConfigDict

class UserResponse(BaseModel):
    username:str
    email:EmailStr

    model_config=ConfigDict(
        from_attributes=True
    )