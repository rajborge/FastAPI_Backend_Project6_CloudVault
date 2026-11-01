import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import get_db
from app.main import app


class FakeDatabase:
    def __init__(self, error=None):
        self.error = error

    def execute(self, statement):
        if self.error is not None:
            raise self.error


@pytest.fixture
def client():
    database = FakeDatabase()

    def override_get_db():
        yield database

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def test_health_liveness_and_readiness(client):
    live_response = client.get("/health/live")
    ready_response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json() == {"status": "ok"}
    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ok", "database": "ok"}


def test_readiness_returns_unavailable_when_database_fails(client):
    def failing_database():
        yield FakeDatabase(SQLAlchemyError("database unavailable"))

    app.dependency_overrides[get_db] = failing_database

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_manual_cleanup_requires_authentication(client):
    response = client.post("/files/cleanup")

    assert response.status_code == 401
