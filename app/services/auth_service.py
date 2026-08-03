from sqlalchemy.orm import Session
from uuid import UUID

from datetime import datetime,UTC

from ..repositories.user import UserRepository
from ..repositories.refresh_token import RefreshTokenRepository
from ..core.security import hash_password,verify_password
from ..core.jwt import create_access_token, create_refresh_token, decode_token
from ..db.models.user import User
from ..db.models.refresh_token import RefreshToken
from ..schemas.auth import RegisterRequest,LoginRequest
from ..core.exceptions import EmailAlreadyExistsException,UsernameAlreadyExistsException,InvalidCredentialsException,InactiveUserException

class AuthService:
    def __init__(self,db:Session):
        self.db=db
        self.user_repository=UserRepository(db)
        self.refresh_repository=RefreshTokenRepository(db)

    def register(self,data:RegisterRequest)->User:
        if self.user_repository.get_user_by_email(data.email):
            raise EmailAlreadyExistsException()
        if self.user_repository.get_user_by_username(data.username):
            raise UsernameAlreadyExistsException()
        user=User(
            username=data.username,
            email=data.email,
            hashed_password=hash_password(data.password),
        )
        try:
            self.user_repository.create(user)
            self.db.commit()
            return user
        except Exception:
            self.db.rollback()
            raise

    def login(self,data:LoginRequest)->str:
        user=self.user_repository.get_by_identifier(data.identifier)

        if user is None:
            raise InvalidCredentialsException()
        if not verify_password(data.password,user.hashed_password):
            raise InvalidCredentialsException()
        if not user.is_active:
            raise InactiveUserException
        access_token=create_access_token(str(user.id))
        refresh_token=create_refresh_token(str(user.id))
        payload=decode_token(refresh_token)
        refresh_token_record=RefreshToken(
            user_id=user.id,
            jti=UUID(payload["jti"]),
            expires_at=datetime.fromtimestamp(
                payload["exp"],
                tz=UTC,
            ),
        )
        refresh_repo=RefreshTokenRepository(self.db)
        refresh_repo.create(refresh_token_record)
        self.db.commit()
        return{
            "access_token":access_token,
            "refresh_token":refresh_token
        }
    
    def refresh(
            self,
            refresh_token:str,
    ):
        payload=decode_token(refresh_token)

        if payload["type"]!="refresh":
            raise InvalidCredentialsException()
        
        jti=UUID(payload["jti"])
        session=self.refresh_repository.get_by_jti(jti)
        if session is None:
            raise InvalidCredentialsException()
        if session.is_revoked:
            raise InvalidCredentialsException()
        if session.expires_at<datetime.now(UTC):
            raise InvalidCredentialsException()
        access_token=create_access_token(str(session.user_id))
        new_refresh_token=create_refresh_token(str(session.user_id))
        new_payload = decode_token(new_refresh_token)

        new_session=RefreshToken(
            user_id=session.user_id,
            jti=UUID(new_payload["jti"]),
            expires_at=datetime.fromtimestamp(
                new_payload["exp"],
                tz=UTC
            ),
        )
        self.refresh_repository.create(new_session)
        self.refresh_repository.revoke_by_jti(jti)
        self.db.commit()
        return{
            "access_token":access_token,
            "refresh_token":new_refresh_token
        }
    
    def logout(
            self,
            refresh_token:str
    ):
        payload=decode_token(refresh_token)
        if payload["type"]!="refresh":
            raise InvalidCredentialsException()
        jti=UUID(payload["jti"])
        session=RefreshTokenRepository.get_by_jti(jti)
        if session is None:
            raise InvalidCredentialsException()
        if session.is_revoked:
            raise InvalidCredentialsException()
        RefreshTokenRepository.revoke_by_jti(jti)
        self.db.commit()