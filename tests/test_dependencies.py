from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.dependencies import (
    get_current_user,
)
from app.core.exceptions import (
    InvalidCredentialsException,
)


def test_refresh_token_cannot_authenticate(
    monkeypatch,
):
    user_id = uuid4()
    jti = uuid4()

    monkeypatch.setattr(
        "app.core.dependencies.decode_token",
        lambda token: {
            "type": "refresh",
            "sub": str(user_id),
            "jti": str(jti),
        },
    )

    credentials = SimpleNamespace(
        credentials="refresh-token"
    )

    db = Mock()

    with pytest.raises(
        InvalidCredentialsException
    ):
        get_current_user(
            credentials=credentials,
            db=db,
        )