from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.exceptions import InvalidUploadException, StorageQuotaExceededException
from app.schemas.file import UploadIntentCreate
from app.services import upload_intent_service as upload_service_module
from app.services.upload_intent_service import UploadIntentService


DIGEST = "b" * 64


def test_completed_intent_retries_do_not_charge_quota_twice():
    service = make_service()
    user = make_user(used=60)
    stored = SimpleNamespace(id=uuid4(), is_deleted=False)
    intent = SimpleNamespace(status="COMPLETED", file_id=stored.id)
    service.intent_repository.get_for_user_for_update.return_value = intent
    service.file_repository.get_by_id.return_value = stored
    assert service.complete_intent(intent_id=uuid4(), user=user, parts=[]) is stored
    assert user.storage_used == 60
    service.user_repository.get_by_id_for_update.assert_not_called()
    service.file_repository.create.assert_not_called()


def test_resuming_multipart_reads_storage_parts_without_reserving_more_quota():
    service = make_service()
    user = make_user(reserved=32)
    intent = SimpleNamespace(id=uuid4(), user_id=user.id, status="OPEN",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        multipart_upload_id="test-upload", object_key="users/test/object",
        mime_type="text/plain", content_sha256=DIGEST, expected_size=32)
    service.intent_repository.get_for_user_for_update.return_value = intent
    service.storage.head_object_if_exists.return_value = None
    service.storage.list_uploaded_parts.return_value = [{"part_number": 1, "etag": "test-etag"}]
    result = service.resume_intent(intent_id=intent.id, user=user)
    assert result['completed_parts'] == [{"part_number": 1, "etag": "test-etag"}]
    assert result['multipart'] is True and result['upload_url'] is None
    assert user.storage_reserved == 32
    service.intent_repository.create.assert_not_called()


def make_service():
    service = UploadIntentService.__new__(UploadIntentService)
    service.storage = Mock()
    service.user_repository = Mock()
    service.intent_repository = Mock()
    service.file_repository = Mock()
    service.folder_repository = Mock()
    service.audit_service = Mock()
    service.db = Mock()
    service.chunk_size_bytes = 16 * 1024 * 1024
    service.multipart_threshold_bytes = 100 * 1024 * 1024
    return service


def make_user(*, used=0, reserved=0, limit=200 * 1024 * 1024):
    return SimpleNamespace(
        id=uuid4(),
        storage_used=used,
        storage_reserved=reserved,
        storage_limit=limit,
    )


def make_intent_data(size):
    return UploadIntentCreate(
        filename="report.pdf",
        mime_type="application/pdf",
        size=size,
        content_sha256=DIGEST,
    )


def test_create_intent_reserves_quota_before_returning_presigned_url():
    service = make_service()
    user = make_user(used=10, reserved=5)
    service.user_repository.get_by_id_for_update.return_value = user
    service.storage.create_upload_url.return_value = "https://r2.test/put"

    data = make_intent_data(32)
    data.content_sha256 = DIGEST.upper()
    response = service.create_intent(user=user, data=data)

    assert response["upload_url"] == "https://r2.test/put"
    assert response["multipart"] is False
    assert user.storage_reserved == 37
    service.intent_repository.create.assert_called_once()
    service.db.commit.assert_called_once()
    service.storage.create_upload_url.assert_called_once()
    stored_intent = service.intent_repository.create.call_args.args[0]
    assert stored_intent.content_sha256 == DIGEST
    assert service.storage.create_upload_url.call_args.kwargs["content_length"] == 32
    assert service.storage.create_upload_url.call_args.kwargs["content_sha256"] == DIGEST


def test_create_intent_rejects_quota_overcommit():
    service = make_service()
    user = make_user(used=10, reserved=5, limit=100)
    service.user_repository.get_by_id_for_update.return_value = user

    with pytest.raises(StorageQuotaExceededException):
        service.create_intent(user=user, data=make_intent_data(86))

    assert user.storage_reserved == 5
    service.storage.create_upload_url.assert_not_called()
    service.db.commit.assert_not_called()


def test_large_intent_starts_multipart_upload():
    service = make_service()
    user = make_user()
    service.user_repository.get_by_id_for_update.return_value = user
    service.storage.create_multipart_upload.return_value = "multipart-1"

    response = service.create_intent(
        user=user,
        data=make_intent_data(service.multipart_threshold_bytes),
    )

    assert response["multipart"] is True
    assert response["upload_url"] is None
    assert response["multipart_upload_id"] == "multipart-1"
    assert user.storage_reserved == service.multipart_threshold_bytes


def test_finalize_converts_reservation_and_creates_pending_scan_file(monkeypatch):
    service = make_service()
    user = make_user(used=40, reserved=60)
    intent = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        folder_id=None,
        object_key=f"users/{user.id}/objects/file-1",
        original_name="report.pdf",
        mime_type="application/pdf",
        expected_size=60,
        content_sha256=DIGEST,
        multipart_upload_id=None,
        status="OPEN",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    service.intent_repository.get_for_user_for_update.return_value = intent
    service.user_repository.get_by_id_for_update.return_value = user
    service.storage.head_object_if_exists.return_value = {
        "size": 60,
        "content_type": "application/pdf",
        "content_sha256": DIGEST,
        "etag": "etag",
    }
    monkeypatch.setattr(
        upload_service_module,
        "File",
        lambda **values: SimpleNamespace(id=uuid4(),**values),
    )
    monkeypatch.setattr(upload_service_module,"enqueue_file_scan",Mock())

    file = service.complete_intent(intent_id=intent.id, user=user, parts=[])

    assert user.storage_reserved == 0
    assert user.storage_used == 100
    assert intent.status == "COMPLETED"
    assert file.storage_backend == "r2"
    assert file.scan_status == "PENDING_SCAN"
    service.file_repository.create.assert_called_once_with(file)
    service.db.commit.assert_called_once()


def test_finalize_rejects_object_with_wrong_size_or_digest():
    service = make_service()
    user = make_user(reserved=60)
    intent = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        folder_id=None,
        object_key="users/file-1",
        original_name="report.pdf",
        mime_type="application/pdf",
        expected_size=60,
        content_sha256=DIGEST,
        multipart_upload_id=None,
        status="OPEN",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    service.intent_repository.get_for_user_for_update.return_value = intent
    service.user_repository.get_by_id_for_update.return_value = user
    service.storage.head_object_if_exists.return_value = {
        "size": 59,
        "content_type": "application/pdf",
        "content_sha256": DIGEST,
        "etag": "etag",
    }

    with pytest.raises(InvalidUploadException):
        service.complete_intent(intent_id=intent.id, user=user, parts=[])

    assert user.storage_reserved == 0
    assert intent.status == "FAILED"
    service.storage.delete_object.assert_called_once_with(object_key=intent.object_key)
    service.file_repository.create.assert_not_called()


def test_expired_multipart_intent_aborts_and_releases_quota():
    service = make_service()
    user = make_user(reserved=60)
    intent = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        object_key="users/file-1",
        expected_size=60,
        multipart_upload_id="multipart-1",
        status="OPEN",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    service.intent_repository.list_expired_open.return_value = [intent]
    service.intent_repository.get_for_user_for_update.return_value = intent
    service.user_repository.get_by_id_for_update.return_value = user
    service.storage.head_object_if_exists.return_value = None

    cleaned = service.cleanup_expired_intents()

    assert cleaned == 1
    assert user.storage_reserved == 0
    assert intent.status == "EXPIRED"
    service.storage.abort_multipart_upload.assert_called_once_with(
        object_key=intent.object_key,
        upload_id="multipart-1",
    )
    service.db.commit.assert_called_once()
