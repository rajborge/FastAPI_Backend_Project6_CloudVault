import secrets

import pyotp
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth_service import AuthService
from app.services.account_service import (
    cipher,
    consume_account_token,
    issue_account_token,
    require_password,
    verify_mfa,
)

router = APIRouter(prefix="/auth", tags=["Account security"])
COOKIE_PATH = "/auth/session"
GENERIC = {"message": "If the account is eligible, an email will arrive shortly."}


@router.get("/email-status")
def email_status(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from sqlalchemy import select
    from app.db.models.collaboration import AccountToken

    latest = db.execute(
        select(AccountToken)
        .where(AccountToken.user_id == current.id, AccountToken.purpose == "verify")
        .order_by(AccountToken.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "email": current.email,
        "is_verified": current.is_verified,
        "delivery_status": latest.delivery_status if latest else "NOT_REQUESTED",
        "delivery_error": latest.delivery_error if latest else None,
        "sent_at": (
            latest.created_at if latest and latest.delivery_status == "SENT" else None
        ),
    }


@router.post("/me/request-verification", status_code=202)
def verify_my_email(tasks: BackgroundTasks, current: User = Depends(get_current_user)):
    if current.is_verified:
        return {"message": "Your email is already verified."}
    tasks.add_task(issue_account_token, current.email, "verify")
    return {"message": "Verification email requested. Check delivery status shortly."}


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ResetRequest(TokenRequest):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        return RegisterRequest.validate_password(value)


class MFARequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{6,64}$")


def check_origin(request: Request):
    allowed = {item.strip() for item in settings.CORS_ORIGINS.split(",")}
    origin = request.headers.get("origin")
    if origin and origin not in allowed:
        raise HTTPException(403, "Origin is not allowed.")


def check_csrf(request: Request):
    check_origin(request)
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get("cloudvault_csrf", "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise HTTPException(403, "Session protection failed. Sign in again.")


def browser_session(response: Response, tokens: dict) -> dict:
    csrf = secrets.token_urlsafe(32)
    for name, value in (
        ("cloudvault_refresh", tokens["refresh_token"]),
        ("cloudvault_csrf", csrf),
    ):
        response.set_cookie(
            name,
            value,
            httponly=True,
            secure=settings.REFRESH_COOKIE_SECURE
            or settings.FILE_SHARE_URL.startswith("https://"),
            samesite="strict",
            path=COOKIE_PATH,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "access_token": tokens["access_token"],
        "csrf_token": csrf,
        "token_type": "Bearer",
    }


def renew_security_session(db, user, response):
    from app.core.jwt import create_access_token, create_refresh_token, decode_token
    from app.db.models.refresh_token import RefreshToken
    from app.repositories.refresh_token import RefreshTokenRepository
    from datetime import datetime, timezone
    from uuid import UUID

    user.auth_version += 1
    RefreshTokenRepository(db).revoke_all_for_user(user.id)
    refresh = create_refresh_token(str(user.id), user.auth_version)
    payload = decode_token(refresh)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=UUID(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc),
        )
    )
    db.commit()
    return browser_session(
        response,
        {
            "access_token": create_access_token(str(user.id), user.auth_version),
            "refresh_token": refresh,
        },
    )


@router.post("/session/login")
def browser_login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    check_origin(request)
    return browser_session(response, AuthService(db).login(data))


@router.post("/session/refresh")
def browser_refresh(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    check_csrf(request)
    return browser_session(
        response, AuthService(db).refresh(request.cookies.get("cloudvault_refresh", ""))
    )


@router.post("/session/logout", status_code=204)
def browser_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    check_csrf(request)
    raw = request.cookies.get("cloudvault_refresh")
    if raw:
        from app.core.jwt import decode_token
        from app.repositories.refresh_token import RefreshTokenRepository
        from uuid import UUID
        from app.core.exceptions import InvalidCredentialsException

        try:
            payload = decode_token(raw)
            if payload.get("type") != "refresh":
                raise InvalidCredentialsException()
            RefreshTokenRepository(db).revoke_by_jti(UUID(payload["jti"]))
            access = request.headers.get("authorization", "").removeprefix("Bearer ")
            if access:
                try:
                    access_payload = decode_token(access)
                    if (
                        access_payload.get("type") == "access"
                        and access_payload["sub"] == payload["sub"]
                    ):
                        from app.db.models.token_blocklist import TokenBlocklist
                        from datetime import datetime, timezone

                        # Avoid duplicate logout records when requests are retried.
                        from sqlalchemy import select

                        if (
                            db.execute(
                                select(TokenBlocklist).where(
                                    TokenBlocklist.jti == UUID(access_payload["jti"])
                                )
                            ).scalar_one_or_none()
                            is None
                        ):
                            db.add(
                                TokenBlocklist(
                                    jti=UUID(access_payload["jti"]),
                                    expires_at=datetime.fromtimestamp(
                                        access_payload["exp"], timezone.utc
                                    ),
                                )
                            )
                except InvalidCredentialsException:
                    pass
            db.commit()
        except (InvalidCredentialsException, KeyError, ValueError):
            db.rollback()
    for name in ("cloudvault_refresh", "cloudvault_csrf"):
        response.delete_cookie(
            name,
            path=COOKIE_PATH,
            secure=settings.REFRESH_COOKIE_SECURE
            or settings.FILE_SHARE_URL.startswith("https://"),
            httponly=True,
            samesite="strict",
        )


@router.post("/forgot-password", status_code=202)
def forgot_password(data: EmailRequest, tasks: BackgroundTasks):
    tasks.add_task(issue_account_token, str(data.email), "reset")
    return GENERIC


@router.post("/request-verification", status_code=202)
def request_verification(data: EmailRequest, tasks: BackgroundTasks):
    tasks.add_task(issue_account_token, str(data.email), "verify")
    return GENERIC


@router.post("/reset-password", status_code=204)
def reset_password(data: ResetRequest, db: Session = Depends(get_db)):
    # Reuse the registration password policy without altering password bytes.
    consume_account_token(db, data.token, "reset", data.password)


@router.post("/verify-email", status_code=204)
def verify_email(data: TokenRequest, db: Session = Depends(get_db)):
    consume_account_token(db, data.token, "verify")


@router.post("/mfa/setup")
def setup_mfa(
    data: MFARequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = UserRepository(db).get_by_id_for_update(current.id)
    require_password(user, data.password)
    if user.mfa_secret:
        raise HTTPException(409, "MFA is already enabled.")
    secret = pyotp.random_base32()
    user.mfa_pending_secret = cipher().encrypt(secret.encode()).decode()
    db.commit()
    return {
        "secret": secret,
        "uri": pyotp.TOTP(secret).provisioning_uri(
            user.email, issuer_name="CloudVault"
        ),
    }


@router.post("/mfa/enable")
def enable_mfa(
    data: MFARequest,
    response: Response,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = UserRepository(db).get_by_id_for_update(current.id)
    require_password(user, data.password)
    verify_mfa(user, data.code, pending=True)
    user.mfa_secret, user.mfa_pending_secret = user.mfa_pending_secret, None
    import hashlib

    recovery_codes = [secrets.token_hex(16) for _ in range(10)]
    user.mfa_recovery_hashes = [
        hashlib.sha256(code.encode()).hexdigest() for code in recovery_codes
    ]
    session = renew_security_session(db, user, response)
    return {**session, "recovery_codes": recovery_codes}


@router.post("/mfa/disable")
def disable_mfa(
    data: MFARequest,
    response: Response,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = UserRepository(db).get_by_id_for_update(current.id)
    require_password(user, data.password)
    verify_mfa(user, data.code)
    user.mfa_secret = user.mfa_pending_secret = None
    user.mfa_last_step = -1
    user.mfa_recovery_hashes = []
    return renew_security_session(db, user, response)
