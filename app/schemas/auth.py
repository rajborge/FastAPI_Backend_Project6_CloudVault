from pydantic import BaseModel,EmailStr,ConfigDict,Field,field_validator
import re

class RegisterRequest(BaseModel):
    username:str=Field(
        min_length=3,
        max_length=30,
        description="Unique Username"
    )

    email:EmailStr

    password:str=Field(
        min_length=8,
        max_length=128,
        description="User Password"
    )

    model_config=ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

class LoginRequest(BaseModel):
    identifier:str=Field(
        min_length=3,
        max_length=255,
        description="Username or Email",
    )

    password:str=Field(
        min_length=8,
        max_length=128,
    )

    model_config=ConfigDict(
        extra="forbid",
        str_strip_whitespace=True
    )

class TokenResponse(BaseModel):
    access_token:str
    refresh_token:str
    token_type:str="Bearer"

class RefreshTokenRequest(BaseModel):
    refresh_token:str

@field_validator("username")
@classmethod
def validate_username(cls,value:str)->str:
    pattern=r"^[A-Za-z][A-Za-z0-9_]{2,29}$"

    if not re.fullmatch(pattern,value):
        raise ValueError(
            "Username must start with a letter and contain only letters,numbers and underscore."
        )
    return value

@field_validator("password")
@classmethod
def validate_password(cls,value:str)->str:
    if not re.search(r"[A-Z]",value):
        raise ValueError("Password must contain atleast one uppercase letter.")
    if not re.search(r"[a-z]",value):
        raise ValueError("Password must contain atleast one lowercase letter.")
    if not re.search(r"\d",value):
        raise ValueError("Password must contain atleast one digit.")
    return value