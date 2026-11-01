"""Single-use account recovery and encrypted, replay-resistant TOTP enrollment."""

import hashlib
import logging
import secrets
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

import pyotp
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.config import settings
from app.core.exceptions import InvalidCredentialsException
from app.core.security import hash_password, verify_password
from app.db.database import SessionLocal
from app.db.models.collaboration import AccountToken
from app.db.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository

logger = logging.getLogger(__name__)


def cipher() -> Fernet:
    if not settings.MFA_ENCRYPTION_KEY:
        raise HTTPException(503, "MFA encryption is not configured.")
    try:
        return Fernet(settings.MFA_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "MFA encryption is not configured.") from None


def verify_mfa(user: User, code: str | None, *, pending=False) -> None:
    encrypted = user.mfa_pending_secret if pending else user.mfa_secret
    if not encrypted or not code:
        raise InvalidCredentialsException()
    if not pending:
        digest = hashlib.sha256(code.encode()).hexdigest()
        for known in user.mfa_recovery_hashes:
            if secrets.compare_digest(digest, known):
                user.mfa_recovery_hashes = [
                    item for item in user.mfa_recovery_hashes if item != known
                ]
                return
    totp = pyotp.TOTP(cipher().decrypt(encrypted.encode()).decode())
    current = int(time.time()) // totp.interval
    # Store the matched step, not just the submitted code, under the User lock.
    matched = next(
        (
            step
            for step in range(current - 1, current + 2)
            if secrets.compare_digest(totp.at(step * totp.interval), code)
        ),
        None,
    )
    if matched is None or matched <= user.mfa_last_step:
        raise InvalidCredentialsException()
    user.mfa_last_step = matched


def send_account_email(recipient: str, token: str, purpose: str) -> None:
    link = (
        settings.account_frontend_url
        + "/?"
        + urlencode({"account_action": purpose, "token": token})
    )
    message = EmailMessage()
    message["Subject"] = "CloudVault: " + (
        "verify your email" if purpose == "verify" else "reset your password"
    )
    message["From"] = settings.MAIL_FROM
    message["To"] = recipient
    message.set_content(
        f"Open this single-use link within 30 minutes:\n{link}\n\nIf you did not request this, ignore this email."
    )
    use_ssl = settings.MAIL_SSL or settings.MAIL_PORT == 465
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    options = {"context": ssl.create_default_context()} if use_ssl else {}
    with smtp_class(
        settings.MAIL_HOST, settings.MAIL_PORT, timeout=15, **options
    ) as smtp:
        if settings.MAIL_STARTTLS and not use_ssl:
            smtp.starttls(context=ssl.create_default_context())
        if settings.MAIL_AUTH_ENABLED:
            password = settings.MAIL_PASSWORD
            if settings.MAIL_HOST.lower() == "smtp.gmail.com":
                password = password.replace(" ", "")
            smtp.login(settings.MAIL_USERNAME, password)
        smtp.send_message(message)


def delivery_error(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed. Check the sender username, app password, and provider account settings."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The email provider rejected the recipient address."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "The provider rejected MAIL_FROM. Use the authenticated sender address or a verified alias."
    if isinstance(exc, ssl.SSLError):
        return "The mail TLS connection failed. Use STARTTLS on port 587 or SSL on port 465."
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return "Could not reach the mail server. Check its host, port, TLS mode, and network access."
    return "The mail provider could not deliver this message. Check the local SMTP configuration."


def issue_account_token(email: str, purpose: str) -> None:
    """Send outside the public response; expose outcomes only to the account owner."""
    with SessionLocal() as db:
        record = None
        try:
            user = db.execute(
                select(User)
                .where(User.email == email, User.is_active.is_(True))
                .with_for_update()
            ).scalar_one_or_none()
            if user is None or (purpose == "verify" and user.is_verified):
                return
            now = datetime.now(timezone.utc)
            latest = db.execute(
                select(AccountToken)
                .where(AccountToken.user_id == user.id, AccountToken.purpose == purpose)
                .order_by(AccountToken.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if (
                latest
                and latest.delivery_status in {"PENDING", "SENT"}
                and not latest.consumed_at
                and latest.created_at > now - timedelta(seconds=60)
            ):
                return
            raw = secrets.token_urlsafe(32)
            record = AccountToken(
                user_id=user.id,
                digest=hashlib.sha256(raw.encode()).hexdigest(),
                purpose=purpose,
                expires_at=now + timedelta(minutes=30),
                delivery_status="PENDING",
            )
            db.add(record)
            db.commit()
            send_account_email(user.email, raw, purpose)
            record.delivery_status, record.delivery_error = "SENT", None
            # Keep earlier links valid if sending fails. Do not invalidate a
            # newer email when concurrent deliveries finish out of order.
            db.execute(
                update(AccountToken)
                .where(
                    AccountToken.user_id == user.id,
                    AccountToken.purpose == purpose,
                    AccountToken.id != record.id,
                    AccountToken.created_at <= record.created_at,
                    AccountToken.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            if record is not None and record.id is not None:
                record.delivery_status = "FAILED"
                record.delivery_error = delivery_error(exc)
                db.commit()
                logger.warning(
                    "Account email delivery failed: %s", record.delivery_error
                )
            else:
                logger.error("Account email request could not be prepared.")


def consume_account_token(
    db, raw: str, purpose: str, password: str | None = None
) -> None:
    token = db.execute(
        select(AccountToken)
        .where(
            AccountToken.digest == hashlib.sha256(raw.encode()).hexdigest(),
            AccountToken.purpose == purpose,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if (
        token is None
        or token.consumed_at
        or token.expires_at <= now
        or token.delivery_status != "SENT"
    ):
        raise HTTPException(400, "This link is invalid or has expired.")
    user = db.execute(
        select(User)
        .where(User.id == token.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    if not user.is_active:
        raise HTTPException(400, "This link is invalid or has expired.")
    if purpose == "verify":
        user.is_verified = True
    else:
        user.hashed_password = hash_password(password)
        user.auth_version += 1
        RefreshTokenRepository(db).revoke_all_for_user(user.id)
        # MFA is deliberately retained; an email reset must not bypass MFA.
    token.consumed_at = now
    db.commit()


def require_password(user: User, password: str) -> None:
    if not user.hashed_password or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsException()
