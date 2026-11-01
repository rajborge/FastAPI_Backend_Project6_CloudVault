import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def integration_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated database ending in _test.")
    if not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError(
            "Integration tests require a disposable database ending in _test."
        )
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    yield engine
    engine.dispose()


@pytest.fixture
def db(integration_engine):
    # Only the explicitly configured disposable database is cleared.
    with integration_engine.begin() as connection:
        connection.execute(
            text("TRUNCATE users, storage_blobs RESTART IDENTITY CASCADE")
        )
    with Session(
        integration_engine, expire_on_commit=False, autoflush=False
    ) as session:
        yield session
        session.rollback()
