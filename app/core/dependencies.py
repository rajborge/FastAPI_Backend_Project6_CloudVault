from uuid import UUID

from fastapi import Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from .jwt import decode_token
from ..core.exceptions import (
    InactiveUserException,
    InvalidCredentialsException,
    UserNotFoundException,
)
from ..db.database import get_db
from ..db.database import SessionLocal
from ..repositories.token_blocklist import (
    TokenBlocklistRepository,
)
from ..repositories.user import UserRepository


bearer_scheme = HTTPBearer()


def get_stream_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    # Streaming responses must not retain the ordinary request-scoped DB
    # dependency for their entire lifetime.
    with SessionLocal() as db:
        return get_current_user(credentials=credentials, db=db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    payload = decode_token(
        credentials.credentials
    )

    if payload.get("type") != "access":
        raise InvalidCredentialsException()

    try:
        jti = UUID(
            payload["jti"]
        )

        user_id = UUID(
            payload["sub"]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        raise InvalidCredentialsException()

    blocklisted = (
        TokenBlocklistRepository(db)
        .get_by_jti(jti)
    )

    if blocklisted is not None:
        raise InvalidCredentialsException()

    user = UserRepository(db).get_by_id(
        user_id
    )

    if user is None:
        raise UserNotFoundException()

    if not user.is_active:
        raise InactiveUserException()

    if payload.get("ver", 0) != user.auth_version:
        raise InvalidCredentialsException()

    return user
