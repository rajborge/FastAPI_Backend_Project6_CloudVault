from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
)
from sqlalchemy.orm import Session

from ..core.dependencies import (
    bearer_scheme,
)
from ..db.database import get_db
from ..schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from ..schemas.user import UserResponse
from ..services.auth_service import (
    AuthService,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    auth_service = AuthService(db)

    return auth_service.register(
        data
    )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    auth_service = AuthService(db)

    tokens = auth_service.login(
        data
    )

    return TokenResponse(
        **tokens
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh(
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    auth_service = AuthService(db)

    tokens = auth_service.refresh(
        data.refresh_token
    )

    return TokenResponse(
        **tokens
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(
    data: RefreshTokenRequest,
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    auth_service = AuthService(db)

    auth_service.logout(
        refresh_token=data.refresh_token,
        access_token=credentials.credentials,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )