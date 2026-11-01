from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.config import settings

from ..core.exceptions import (
    EmailAlreadyExistsException,
    InactiveUserException,
    InvalidCredentialsException,
    UsernameAlreadyExistsException,
)
from ..core.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from ..core.security import (
    hash_password,
    verify_password,
)
from ..db.models.refresh_token import RefreshToken
from ..db.models.token_blocklist import TokenBlocklist
from ..db.models.user import User
from ..repositories.refresh_token import RefreshTokenRepository
from ..repositories.token_blocklist import TokenBlocklistRepository
from ..repositories.user import UserRepository
from ..schemas.auth import LoginRequest, RegisterRequest


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repository = UserRepository(db)
        self.refresh_repository = RefreshTokenRepository(db)
        self.blocklist_repository = TokenBlocklistRepository(db)

    def register(self, data: RegisterRequest) -> User:
        if self.user_repository.get_user_by_email(data.email):
            raise EmailAlreadyExistsException()

        if self.user_repository.get_user_by_username(data.username):
            raise UsernameAlreadyExistsException()

        user = User(
            username=data.username,
            email=data.email,
            hashed_password=hash_password(data.password),
        )

        try:
            self.user_repository.create(user)
            self.db.commit()
            self.db.refresh(user)

            return user

        except Exception:
            self.db.rollback()
            raise

    def login(self, data: LoginRequest) -> dict:
        user = self.user_repository.get_by_identifier(
            data.identifier
        )

        if user is None:
            raise InvalidCredentialsException()

        if user.hashed_password is None:
            raise InvalidCredentialsException()

        if not verify_password(
            data.password,
            user.hashed_password,
        ):
            raise InvalidCredentialsException()

        if not user.is_active:
            raise InactiveUserException()

        if settings.REQUIRE_VERIFIED_EMAIL and not user.is_verified:
            raise HTTPException(403, "Verify your email before signing in.")
        if getattr(user, "mfa_secret", None):
            from app.services.account_service import verify_mfa
            user = self.user_repository.get_by_id_for_update(user.id)
            verify_mfa(user, data.mfa_code)

        access_token = create_access_token(
            str(user.id), auth_version=getattr(user, "auth_version", 0) or 0
        )

        refresh_token = create_refresh_token(
            str(user.id), auth_version=getattr(user, "auth_version", 0) or 0
        )

        refresh_payload = decode_token(
            refresh_token
        )

        try:
            refresh_token_record = RefreshToken(
                user_id=user.id,
                jti=UUID(
                    refresh_payload["jti"]
                ),
                expires_at=datetime.fromtimestamp(
                    refresh_payload["exp"],
                    tz=UTC,
                ),
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            raise InvalidCredentialsException()

        try:
            self.refresh_repository.create(
                refresh_token_record
            )

            user.last_login_at = datetime.now(
                UTC
            )

            self.db.commit()

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
            }

        except Exception:
            self.db.rollback()
            raise

    def refresh(
        self,
        refresh_token: str,
    ) -> dict:
        payload = decode_token(
            refresh_token
        )

        if payload.get("type") != "refresh":
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

        session = self.refresh_repository.get_by_jti_for_update(
            jti
        )

        if session is None:
            raise InvalidCredentialsException()

        if session.user_id != user_id:
            raise InvalidCredentialsException()

        if session.is_revoked:
            # A consumed token has been presented again. Revoke every successor
            # for this account instead of letting a stolen session survive.
            self.refresh_repository.revoke_all_for_user(user_id)
            self.user_repository.invalidate_access(user_id)
            self.db.commit()
            raise InvalidCredentialsException()

        if session.expires_at < datetime.now(
            UTC
        ):
            raise InvalidCredentialsException()

        user = self.user_repository.get_by_id(
            user_id
        )

        if user is None:
            raise InvalidCredentialsException()

        if not user.is_active:
            raise InactiveUserException()
        if payload.get("ver", 0) != (getattr(user, "auth_version", 0) or 0):
            raise InvalidCredentialsException()

        access_token = create_access_token(
            str(user.id), auth_version=getattr(user, "auth_version", 0) or 0
        )

        new_refresh_token = create_refresh_token(
            str(user.id), auth_version=getattr(user, "auth_version", 0) or 0
        )

        new_payload = decode_token(
            new_refresh_token
        )

        try:
            new_refresh_jti = UUID(
                new_payload["jti"]
            )

            new_refresh_expires_at = (
                datetime.fromtimestamp(
                    new_payload["exp"],
                    tz=UTC,
                )
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            raise InvalidCredentialsException()

        new_session = RefreshToken(
            user_id=user.id,
            jti=new_refresh_jti,
            expires_at=new_refresh_expires_at,
        )

        try:
            self.refresh_repository.create(
                new_session
            )

            self.refresh_repository.revoke_by_jti(
                jti
            )

            self.db.commit()

            return {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
            }

        except Exception:
            self.db.rollback()
            raise

    def logout(
        self,
        refresh_token: str,
        access_token: str,
    ) -> None:
        refresh_payload = decode_token(
            refresh_token
        )

        access_payload = decode_token(
            access_token
        )

        if refresh_payload.get(
            "type"
        ) != "refresh":
            raise InvalidCredentialsException()

        if access_payload.get(
            "type"
        ) != "access":
            raise InvalidCredentialsException()

        try:
            refresh_jti = UUID(
                refresh_payload["jti"]
            )

            access_jti = UUID(
                access_payload["jti"]
            )

            refresh_user_id = UUID(
                refresh_payload["sub"]
            )

            access_user_id = UUID(
                access_payload["sub"]
            )

            access_expires_at = (
                datetime.fromtimestamp(
                    access_payload["exp"],
                    tz=UTC,
                )
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            raise InvalidCredentialsException()

        if refresh_user_id != access_user_id:
            raise InvalidCredentialsException()

        session = self.refresh_repository.get_by_jti(
            refresh_jti
        )

        if session is None:
            raise InvalidCredentialsException()

        if session.user_id != refresh_user_id:
            raise InvalidCredentialsException()

        if session.is_revoked:
            raise InvalidCredentialsException()

        existing_blocklist = (
            self.blocklist_repository.get_by_jti(
                access_jti
            )
        )

        try:
            self.refresh_repository.revoke_by_jti(
                refresh_jti
            )

            if existing_blocklist is None:
                blocked_token = TokenBlocklist(
                    jti=access_jti,
                    expires_at=access_expires_at,
                )

                self.blocklist_repository.create(
                    blocked_token
                )

            self.db.commit()

        except Exception:
            self.db.rollback()
            raise
