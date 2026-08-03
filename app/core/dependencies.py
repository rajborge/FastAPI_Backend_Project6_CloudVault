from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from sqlalchemy.orm import Session
from uuid import UUID

from .jwt import decode_token
from ..db.database import get_db
from ..db.models.user import User
from ..repositories.user import UserRepository
from ..repositories.token_blocklist import TokenBlocklistRepository
from ..core.exceptions import UserNotFoundException,InvalidCredentialsException

bearer_scheme=HTTPBearer()

def get_current_user(
        credentials:HTTPAuthorizationCredentials=Depends(bearer_scheme),
        db:Session=Depends(get_db),
):
    payload=decode_token(credentials.credentials)
    print("Payload",payload)
    jti=UUID(payload["jti"])
    blocklisted=(
        TokenBlocklistRepository(db)
        .get_by_jti(UUID(payload["jti"]))
    )
    print("Blocked",blocklisted)
    if blocklisted:
        raise InvalidCredentialsException()
    user_id=UUID(payload["sub"])
    user=UserRepository(db).get_by_id(user_id)

    if user is None:
        raise UserNotFoundException()
    return user