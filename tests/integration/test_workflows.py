from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.collaboration import add_version, restore_version, VersionRequest
from app.core.config import settings
from app.core.exceptions import (
    InvalidCredentialsException,
    StorageQuotaExceededException,
)
from app.core.jwt import create_refresh_token, decode_token
from app.core.security import hash_password
from app.db.database import get_db
from app.db.models.collaboration import AccountToken, Comment
from app.db.models.file import File
from app.db.models.refresh_token import RefreshToken
from app.db.models.user import User
from app.main import app
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest
from app.schemas.file import UploadIntentCreate
from app.services.account_service import consume_account_token, verify_mfa
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.upload_intent_service import UploadIntentService


def user(db, name="tester", **values):
    obj = User(
        username=name,
        email=f"{name}@example.com",
        hashed_password=hash_password("Password1"),
        **values,
    )
    db.add(obj)
    db.commit()
    return obj


def file(db, owner, tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    obj = File(
        user_id=owner.id,
        original_name=name,
        stored_name=name,
        storage_path=str(path),
        mime_type="text/plain",
        size=len(data),
        scan_status="CLEAN",
        content_sha256=sha256(data).hexdigest(),
    )
    owner.storage_used += len(data)
    db.add(obj)
    db.commit()
    return obj


def test_concurrent_quota_reservations_refresh_stale_identity(db, integration_engine):
    owner = user(db, storage_limit=100)
    barrier = Barrier(2)

    def reserve():
        with Session(integration_engine, expire_on_commit=False) as session:
            stale = session.get(User, owner.id)
            assert stale.storage_reserved == 0
            barrier.wait(timeout=5)
            storage = SimpleNamespace(
                create_upload_url=lambda **_: "https://storage.example.test/put"
            )
            service = UploadIntentService(session, storage=storage)
            try:
                service.create_intent(
                    user=stale,
                    data=UploadIntentCreate(
                        filename="a.txt",
                        mime_type="text/plain",
                        size=60,
                        content_sha256="a" * 64,
                    ),
                )
                return "reserved"
            except StorageQuotaExceededException:
                session.rollback()
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(results) == ["rejected", "reserved"]
    db.refresh(owner)
    assert owner.storage_reserved == 60


def test_atomic_storage_release_does_not_lose_concurrent_updates(
    db, integration_engine
):
    owner = user(db, storage_used=100)

    def release():
        with Session(integration_engine) as session:
            session.get(User, owner.id)
            UserRepository(session).release_storage(owner.id, 30)
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: release(), range(2)))
    db.refresh(owner)
    assert owner.storage_used == 40


def test_refresh_token_cannot_be_rotated_twice_concurrently(db, integration_engine):
    owner = user(db)
    raw = create_refresh_token(str(owner.id))
    payload = decode_token(raw)
    db.add(
        RefreshToken(
            user_id=owner.id,
            jti=payload["jti"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    db.commit()
    barrier = Barrier(2)

    def rotate():
        with Session(integration_engine) as session:
            barrier.wait(timeout=5)
            try:
                AuthService(session).refresh(raw)
                return True
            except InvalidCredentialsException:
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))
    assert sorted(results) == [False, True]
    assert all(t.is_revoked for t in db.execute(select(RefreshToken)).scalars())


def test_reset_token_single_use_and_invalidates_access(db):
    owner = user(db)
    raw = "x" * 43
    db.add(
        AccountToken(
            user_id=owner.id,
            digest=sha256(raw.encode()).hexdigest(),
            purpose="reset",
            delivery_status="SENT",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
    )
    db.commit()
    consume_account_token(db, raw, "reset", "ChangedPassword2")
    assert owner.auth_version == 1
    with pytest.raises(HTTPException):
        consume_account_token(db, raw, "reset", "AnotherPassword3")


def test_mfa_rejects_replay_and_bad_codes(db, monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "MFA_ENCRYPTION_KEY", key.decode())
    secret = pyotp.random_base32()
    owner = user(db, mfa_secret=Fernet(key).encrypt(secret.encode()).decode())
    verify_mfa(owner, pyotp.TOTP(secret).now())
    with pytest.raises(InvalidCredentialsException):
        verify_mfa(owner, pyotp.TOTP(secret).now())
    with pytest.raises(InvalidCredentialsException):
        verify_mfa(owner, "bad")


def test_version_restore_preserves_quota_and_delete_cleans_history(
    db, tmp_path, monkeypatch
):
    owner = user(db)
    first = file(db, owner, tmp_path, "original.txt", b"old")
    incoming = file(db, owner, tmp_path, "replacement.txt", b"newer")
    monkeypatch.setattr("app.api.collaboration.enqueue_file_index", lambda _: True)
    total = owner.storage_used
    add_version(first.id, VersionRequest(source_file_id=incoming.id), owner, db)
    assert first.size == 5 and incoming.size == 3 and incoming.version_of == first.id
    db.refresh(owner)
    assert owner.storage_used == total
    restore_version(first.id, incoming.id, owner, db)
    assert first.size == 3 and incoming.size == 5
    service = FileService(db)
    service.delete_file(file_id=first.id, user=owner)
    service.permanently_delete_file(file_id=first.id, user=owner)
    db.refresh(owner)
    assert owner.storage_used == 0
    assert db.get(File, first.id) is None
    assert db.get(File, incoming.id) is None
    assert not (tmp_path / "original.txt").exists()
    assert not (tmp_path / "replacement.txt").exists()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_browser_session_cookie_csrf_and_logout(client, db):
    user(db)
    response = client.post(
        "/auth/session/login",
        json={"identifier": "tester", "password": "Password1"},
        headers={"origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert "refresh_token" not in response.json()
    cookies = response.headers.get_list("set-cookie")
    assert all("HttpOnly" in c and "SameSite=strict" in c for c in cookies)
    assert client.post("/auth/session/refresh").status_code == 403
    csrf = response.json()["csrf_token"]
    refreshed = client.post("/auth/session/refresh", headers={"x-csrf-token": csrf})
    assert refreshed.status_code == 200
    logged_out = client.post(
        "/auth/session/logout",
        headers={
            "x-csrf-token": refreshed.json()["csrf_token"],
            "authorization": "Bearer " + refreshed.json()["access_token"],
        },
    )
    assert logged_out.status_code == 204


def test_comment_access_control(client, db, tmp_path):
    owner = user(db)
    target = file(db, owner, tmp_path, "notes.txt", b"notes")
    stranger = user(db, "stranger")
    from app.core.jwt import create_access_token

    headers = {"authorization": "Bearer " + create_access_token(str(stranger.id))}
    response = client.post(
        f"/files/{target.id}/comments", headers=headers, json={"body": "hello"}
    )
    assert response.status_code == 403
    headers = {"authorization": "Bearer " + create_access_token(str(owner.id))}
    assert (
        client.post(
            f"/files/{target.id}/comments", headers=headers, json={"body": "hello"}
        ).status_code
        == 201
    )
    assert (
        client.get(f"/files/{target.id}/comments", headers=headers).json()[0]["body"]
        == "hello"
    )


def test_r2_share_redirect_uses_get(client, db, tmp_path, monkeypatch):
    from app.services.shared_file_service import SharedFileService

    monkeypatch.setattr(
        SharedFileService,
        "get_shared_file",
        lambda *a, **k: (SimpleNamespace(), "https://storage.example.test/signed-get"),
    )
    response = client.post(
        "/shares/test-capability/download",
        json={"password": "test"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "https://storage.example.test/signed-get"


def test_search_finds_indexed_text_without_leaking_other_users(db, tmp_path):
    from app.services.search_service import (
        SearchService,
        hashed_text_vector,
        vector_literal,
    )

    owner = user(db)
    other = user(db, "other")
    target = file(db, owner, tmp_path, "notes.txt", b"moonlight")
    db.execute(
        text(
            "INSERT INTO file_search_documents(file_id, extracted_text, embedding) VALUES (:id, :text, CAST(:vector AS vector))"
        ),
        {
            "id": target.id,
            "text": "moonlight",
            "vector": vector_literal(hashed_text_vector("moonlight")),
        },
    )
    db.commit()
    assert SearchService(db).search(user=owner, query="moonlight")[0]["id"] == target.id
    assert SearchService(db).search(user=other, query="moonlight") == []


def test_mfa_recovery_code_is_consumed_once(db, monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "MFA_ENCRYPTION_KEY", key.decode())
    raw = "f" * 32
    owner = user(
        db,
        mfa_secret=Fernet(key).encrypt(pyotp.random_base32().encode()).decode(),
        mfa_recovery_hashes=[sha256(raw.encode()).hexdigest()],
    )
    verify_mfa(owner, raw)
    assert owner.mfa_recovery_hashes == []
    with pytest.raises(InvalidCredentialsException):
        verify_mfa(owner, raw)


def test_recovery_requeues_abandoned_jobs_and_clears_old_leases(
    db, integration_engine, tmp_path, monkeypatch
):
    from app.tasks import recovery

    owner = user(db)
    target = file(db, owner, tmp_path, "abandoned.txt", b"queued")
    target.scan_status = "SCANNING"
    target.scan_started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    target.scan_lease = uuid4()
    db.commit()
    queued = []
    monkeypatch.setattr(
        recovery,
        "SessionLocal",
        lambda: Session(integration_engine, expire_on_commit=False),
    )
    monkeypatch.setattr(
        recovery, "enqueue_file_scan", lambda file_id: queued.append(file_id) or True
    )
    assert recovery.recover_jobs()["scan"] == 1
    assert queued == [target.id]
    db.refresh(target)
    assert target.scan_status == "PENDING_SCAN" and target.scan_lease is None


def test_rate_limiting_uses_redis_and_returns_retry_after(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(settings, "SECRET_KEY", str(uuid4()))
    assert client.get("/shares/missing").status_code == 404
    result = client.get("/shares/missing", headers={"origin": "http://localhost:5173"})
    assert result.status_code == 429 and int(result.headers["retry-after"]) > 0
    assert result.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_mfa_enrollment_invalidates_old_sessions_and_returns_recovery_codes(
    client, db, monkeypatch
):
    from app.core.jwt import create_access_token

    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "MFA_ENCRYPTION_KEY", key.decode())
    owner = user(db)
    secret = pyotp.random_base32()
    owner.mfa_pending_secret = Fernet(key).encrypt(secret.encode()).decode()
    db.commit()
    old = create_access_token(str(owner.id))
    headers = {"authorization": "Bearer " + old}
    response = client.post(
        "/auth/mfa/enable",
        headers=headers,
        json={"password": "Password1", "code": pyotp.TOTP(secret).now()},
    )
    assert response.status_code == 200
    assert len(response.json()["recovery_codes"]) == 10
    assert client.get("/users/me", headers=headers).status_code == 401
    new_headers = {"authorization": "Bearer " + response.json()["access_token"]}
    assert client.get("/users/me", headers=new_headers).status_code == 200


def test_deleting_versions_releases_a_shared_blob_exactly_once(
    db, tmp_path, monkeypatch
):
    from app.repositories.storage_blob_repository import StorageBlobRepository
    from app.db.models.storage_blob import StorageBlob

    owner = user(db)
    original = file(db, owner, tmp_path, "first.txt", b"same")
    incoming = file(db, owner, tmp_path, "second.txt", b"same")
    repository = StorageBlobRepository(db)
    for row in (original, incoming):
        repository.attach_clean_file(
            file=row, content_sha256=sha256(b"same").hexdigest()
        )
        db.commit()
    blob = db.execute(select(StorageBlob)).scalar_one()
    assert blob.reference_count == 2
    monkeypatch.setattr("app.api.collaboration.enqueue_file_index", lambda _: True)
    add_version(original.id, VersionRequest(source_file_id=incoming.id), owner, db)
    service = FileService(db)
    service.delete_file(file_id=original.id, user=owner)
    service.permanently_delete_file(file_id=original.id, user=owner)
    assert db.execute(select(StorageBlob)).scalar_one_or_none() is None
    db.refresh(owner)
    assert owner.storage_used == 0


@pytest.mark.parametrize(
    "role,comment,edit",
    [("viewer", False, False), ("commenter", True, False), ("editor", True, True)],
)
def test_recipient_download_and_role_visibility(
    client, db, tmp_path, role, comment, edit
):
    from app.core.jwt import create_access_token

    owner = user(db, "sender")
    receiver = user(db, "recipient")
    target = file(db, owner, tmp_path, "shared.txt", b"file contents")
    owner_headers = {"authorization": "Bearer " + create_access_token(str(owner.id))}
    receiver_headers = {
        "authorization": "Bearer " + create_access_token(str(receiver.id))
    }
    grant = client.post(
        "/permissions",
        headers=owner_headers,
        json={
            "target_identifier": receiver.email,
            "resource_type": "file",
            "resource_id": str(target.id),
            "role": role,
        },
    )
    assert grant.status_code == 200 and grant.json()["username"] == "recipient"
    received = client.get(
        "/permissions/shared-with-me", headers=receiver_headers
    ).json()[0]
    assert (
        received["owner_username"] == "sender"
        and received["recipient_username"] == "recipient"
    )
    assert (
        received["capabilities"]["can_download"]
        and received["capabilities"]["can_comment"] is comment
    )
    assert received["capabilities"]["can_edit"] is edit
    assert not received["capabilities"]["can_manage_access"]
    sent = client.get("/permissions/shared-by-me", headers=owner_headers).json()[0]
    assert sent["recipient_email"] == receiver.email
    link = client.get(f"/files/{target.id}/download-link", headers=receiver_headers)
    assert link.status_code == 200 and not link.json()["external"]
    download = client.get(link.json()["url"], headers=receiver_headers)
    assert download.status_code == 200 and download.content == b"file contents"
    preview = client.get(
        f"/files/{target.id}/download-link?preview=true", headers=receiver_headers
    )
    assert (
        client.get(preview.json()["url"], headers=receiver_headers).status_code == 200
    )
    assert (
        client.get(
            f"/permissions?resource_type=file&resource_id={target.id}",
            headers=receiver_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/permissions",
            headers=owner_headers,
            json={
                "target_identifier": receiver.email,
                "resource_type": "file",
                "resource_id": str(target.id),
                "role": "owner",
            },
        ).status_code
        == 422
    )


def test_verification_failure_status_and_successful_retry(
    client, db, integration_engine, monkeypatch
):
    from app.services import account_service
    from app.core.jwt import create_access_token
    import smtplib

    owner = user(db)
    monkeypatch.setattr(
        account_service,
        "SessionLocal",
        lambda: Session(integration_engine, expire_on_commit=False),
    )

    def failed(*args):
        raise smtplib.SMTPAuthenticationError(535, b"private-value")

    monkeypatch.setattr(account_service, "send_account_email", failed)
    account_service.issue_account_token(owner.email, "verify")
    headers = {"authorization": "Bearer " + create_access_token(str(owner.id))}
    status = client.get("/auth/email-status", headers=headers).json()
    assert (
        status["delivery_status"] == "FAILED"
        and "private-value" not in status["delivery_error"]
    )
    delivered = []
    monkeypatch.setattr(
        account_service,
        "send_account_email",
        lambda email, raw, purpose: delivered.append(raw),
    )
    account_service.issue_account_token(owner.email, "verify")
    assert (
        client.get("/auth/email-status", headers=headers).json()["delivery_status"]
        == "SENT"
    )
    assert (
        client.post("/auth/verify-email", json={"token": delivered[0]}).status_code
        == 204
    )
    assert (
        client.get("/auth/email-status", headers=headers).json()["is_verified"] is True
    )
