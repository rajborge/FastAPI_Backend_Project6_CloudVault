from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..schemas.auth import RegisterRequest,TokenResponse,LoginRequest,RefreshTokenRequest
from ..schemas.user  import UserResponse
from ..services.auth_service import AuthService

router=APIRouter(prefix="/auth",tags=["Authentication"])

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201
)
def register(data:RegisterRequest,db:Session=Depends(get_db)):
    auth_service=AuthService(db)

    return auth_service.register(data)

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data:LoginRequest,
    db:Session=Depends(get_db),
):
    auth_service=AuthService(db)

    tokens=auth_service.login(data)
    return TokenResponse(**tokens)

@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh(
    data:RefreshTokenRequest,
    db:Session=Depends(get_db),
):
    auth_service=AuthService(db)
    tokens=auth_service.refresh(data.refresh_token)
    return TokenResponse(**tokens)