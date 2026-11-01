from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from .config import settings
from .exceptions import InvalidCredentialsException


def create_token(
    user_id: str,
    token_type: str,
    expires_delta: timedelta,
    auth_version: int = 0,
) -> str:
    now = datetime.now(UTC)

    payload = {
        "sub": user_id,
        "ver": auth_version,
        "jti": str(uuid4()),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_access_token(
    user_id: str,
    auth_version: int = 0,
) -> str:
    return create_token(
        user_id=user_id,
        auth_version=auth_version,
        token_type="access",
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    )


def create_refresh_token(
    user_id: str,
    auth_version: int = 0,
) -> str:
    return create_token(
        user_id=user_id,
        auth_version=auth_version,
        token_type="refresh",
        expires_delta=timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[
                settings.ALGORITHM
            ],
            options={"require": ["sub", "jti", "type", "iat", "exp"]},
        )

    except ExpiredSignatureError:
        raise InvalidCredentialsException()

    except InvalidTokenError:
        raise InvalidCredentialsException()
