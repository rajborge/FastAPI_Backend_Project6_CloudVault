from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    EmailAlreadyExistsException,
    InactiveUserException,
    InvalidCredentialsException,
    UsernameAlreadyExistsException,
)
from app.core.jwt import decode_token
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
)
from app.services.auth_service import AuthService


def make_service():
    service = AuthService.__new__(AuthService)

    service.db = Mock()
    service.user_repository = Mock()
    service.refresh_repository = Mock()
    service.blocklist_repository = Mock()

    return service

def test_logout_revokes_refresh_and_blocklists_access(
    monkeypatch,
):
    service = make_service()

    user_id = uuid4()
    refresh_jti = uuid4()
    access_jti = uuid4()

    refresh_session = Mock()
    refresh_session.user_id = user_id
    refresh_session.is_revoked = False

    service.refresh_repository.get_by_jti.return_value = (
        refresh_session
    )

    service.blocklist_repository.get_by_jti.return_value = (
        None
    )

    def fake_decode(token):
        if token == "refresh-token":
            return {
                "type": "refresh",
                "jti": str(
                    refresh_jti
                ),
                "sub": str(
                    user_id
                ),
                "exp": 9999999999,
            }

        return {
            "type": "access",
            "jti": str(
                access_jti
            ),
            "sub": str(
                user_id
            ),
            "exp": 9999999999,
        }

    monkeypatch.setattr(
        "app.services.auth_service.decode_token",
        fake_decode,
    )

    service.logout(
        refresh_token="refresh-token",
        access_token="access-token",
    )

    service.refresh_repository.revoke_by_jti.assert_called_once_with(
        refresh_jti
    )

    service.blocklist_repository.create.assert_called_once()

    service.db.commit.assert_called_once()


def test_register_creates_user(monkeypatch):
    service = make_service()

    service.user_repository.get_user_by_email.return_value = None
    service.user_repository.get_user_by_username.return_value = None

    monkeypatch.setattr(
        "app.services.auth_service.hash_password",
        lambda password: f"hashed:{password}",
    )

    data = RegisterRequest(
        username="Pranav_123",
        email="pranav@example.com",
        password="Password1",
    )

    user = service.register(data)

    assert user.username == "Pranav_123"
    assert user.email == "pranav@example.com"
    assert user.hashed_password == "hashed:Password1"

    service.user_repository.create.assert_called_once()

    service.db.commit.assert_called_once()


def test_register_rejects_duplicate_email():
    service = make_service()

    service.user_repository.get_user_by_email.return_value = (
        SimpleNamespace()
    )

    data = RegisterRequest(
        username="Pranav_123",
        email="pranav@example.com",
        password="Password1",
    )

    with pytest.raises(
        EmailAlreadyExistsException
    ):
        service.register(data)


def test_register_rejects_duplicate_username():
    service = make_service()

    service.user_repository.get_user_by_email.return_value = None

    service.user_repository.get_user_by_username.return_value = (
        SimpleNamespace()
    )

    data = RegisterRequest(
        username="Pranav_123",
        email="pranav@example.com",
        password="Password1",
    )

    with pytest.raises(
        UsernameAlreadyExistsException
    ):
        service.register(data)


def test_login_with_valid_credentials(
    monkeypatch,
):
    service = make_service()

    user = SimpleNamespace(
        id=uuid4(),
        hashed_password="hashed",
        is_active=True,
        last_login_at=None,
    )

    service.user_repository.get_by_identifier.return_value = user

    monkeypatch.setattr(
        "app.services.auth_service.verify_password",
        lambda password, hashed: True,
    )

    service.refresh_repository.create = Mock()

    result = service.login(
        LoginRequest(
            identifier="Pranav_123",
            password="Password1",
        )
    )

    assert result["access_token"]
    assert result["refresh_token"]

    access_payload = decode_token(
        result["access_token"]
    )

    refresh_payload = decode_token(
        result["refresh_token"]
    )

    assert access_payload["type"] == "access"
    assert refresh_payload["type"] == "refresh"

    assert access_payload["sub"] == str(
        user.id
    )

    assert refresh_payload["sub"] == str(
        user.id
    )

    service.refresh_repository.create.assert_called_once()

    assert user.last_login_at is not None

    service.db.commit.assert_called_once()


def test_login_rejects_unknown_user():
    service = make_service()

    service.user_repository.get_by_identifier.return_value = None

    with pytest.raises(
        InvalidCredentialsException
    ):
        service.login(
            LoginRequest(
                identifier="unknown",
                password="Password1",
            )
        )


def test_login_rejects_wrong_password(
    monkeypatch,
):
    service = make_service()

    user = SimpleNamespace(
        id=uuid4(),
        hashed_password="hashed",
        is_active=True,
    )

    service.user_repository.get_by_identifier.return_value = user

    monkeypatch.setattr(
        "app.services.auth_service.verify_password",
        lambda password, hashed: False,
    )

    with pytest.raises(
        InvalidCredentialsException
    ):
        service.login(
            LoginRequest(
                identifier="Pranav_123",
                password="WrongPass1",
            )
        )


def test_login_rejects_inactive_user(
    monkeypatch,
):
    service = make_service()

    user = SimpleNamespace(
        id=uuid4(),
        hashed_password="hashed",
        is_active=False,
    )

    service.user_repository.get_by_identifier.return_value = user

    monkeypatch.setattr(
        "app.services.auth_service.verify_password",
        lambda password, hashed: True,
    )

    with pytest.raises(
        InactiveUserException
    ):
        service.login(
            LoginRequest(
                identifier="Pranav_123",
                password="Password1",
            )
        )


def test_register_username_validation():
    with pytest.raises(ValueError):
        RegisterRequest(
            username="123pranav",
            email="pranav@example.com",
            password="Password1",
        )


def test_register_password_requires_uppercase():
    with pytest.raises(ValueError):
        RegisterRequest(
            username="Pranav_123",
            email="pranav@example.com",
            password="password1",
        )


def test_register_password_requires_lowercase():
    with pytest.raises(ValueError):
        RegisterRequest(
            username="Pranav_123",
            email="pranav@example.com",
            password="PASSWORD1",
        )


def test_register_password_requires_number():
    with pytest.raises(ValueError):
        RegisterRequest(
            username="Pranav_123",
            email="pranav@example.com",
            password="Password",
        )